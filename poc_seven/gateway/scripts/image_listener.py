#!/usr/bin/env python3
"""
Image Listener Service

Polls the PACS database for new DICOM images, generates thumbnails,
and sends structured image_received messages.
"""

import base64
import logging
import os
import signal
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
import uuid
from datetime import datetime, timezone

from relay_event_sender import send_image_event_sync
from thumbnail_generator import generate_thumbnail

# Setup logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("image_listener")

# Configuration
PACS_DB_PATH = os.getenv("PACS_DB_PATH", "/var/lib/pacs/pacs.db")
PACS_STORAGE_ROOT = Path(os.getenv("PACS_STORAGE_ROOT", "/var/lib/pacs/storage"))
THUMBNAIL_ROOT = Path(os.getenv("THUMBNAIL_ROOT", "/var/lib/pacs/thumbnails"))
WORKLIST_DB_PATH = os.getenv("WORKLIST_DB_PATH", "/var/lib/worklist/worklist.db")
POLL_INTERVAL = int(os.getenv("IMAGE_POLL_INTERVAL", "2"))  # seconds
BATCH_SIZE = int(os.getenv("IMAGE_BATCH_SIZE", "10"))
THUMBNAIL_QUALITY = int(os.getenv("THUMBNAIL_QUALITY", "25"))
THUMBNAIL_HEIGHT = int(os.getenv("THUMBNAIL_HEIGHT", "188"))

# Shutdown flag
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger.info(f"Received signal {signum}, shutting down gracefully...")
    shutdown_requested = True


@contextmanager
def get_db_connection():
    """Get a database connection with proper error handling."""
    conn = None
    try:
        conn = sqlite3.connect(PACS_DB_PATH, timeout=30.0)
        conn.row_factory = sqlite3.Row
        yield conn
    finally:
        if conn:
            conn.close()


def get_pending_images(limit=BATCH_SIZE):
    """
    Get instances that need processing (thumbnail + message sending).

    Returns list of dicts with full instance metadata.
    """
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT *
            FROM stored_instances
            WHERE thumbnail_status = 'PENDING'
              AND status = 'STORED'
            ORDER BY received_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


def mark_image_processed(sop_instance_uid: str):
    """Mark image as successfully processed (thumbnail + message sent)."""
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE stored_instances
            SET thumbnail_status = 'GENERATED',
                thumbnail_generated_at = CURRENT_TIMESTAMP,
                thumbnail_error = NULL
            WHERE sop_instance_uid = ?
            """,
            (sop_instance_uid,),
        )
        conn.commit()
    logger.info(f"Marked image as processed: {sop_instance_uid}")


def mark_image_failed(sop_instance_uid: str, error: str):
    """Mark image processing as failed."""
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE stored_instances
            SET thumbnail_status = 'FAILED',
                thumbnail_error = ?
            WHERE sop_instance_uid = ?
            """,
            (error[:500], sop_instance_uid),
        )
        conn.commit()
    logger.warning(f"Marked image as failed: {sop_instance_uid} - {error}")


def encode_thumbnail_base64(thumbnail_path: Path) -> Optional[str]:
    """
    Read thumbnail and encode as base64.

    Args:
        thumbnail_path: Path to thumbnail JPEG file

    Returns:
        Base64 encoded string, or None if file doesn't exist
    """
    try:
        if not thumbnail_path.exists():
            return None
        return base64.b64encode(thumbnail_path.read_bytes()).decode('utf-8')
    except Exception as e:
        logger.error(f"Error encoding thumbnail: {e}")
        return None




def get_action_id_for_accession(accession_number: Optional[str]) -> Optional[str]:
    """
    Look up the original action_id from worklist database by accession number.

    This links the image back to the original worklist creation action
    sent from manage-screening, enabling proper event tracking.

    Args:
        accession_number: The accession number from the DICOM image

    Returns:
        The action_id (source_message_id) if found, None otherwise
    """
    if not accession_number:
        return None

    try:
        conn = sqlite3.connect(WORKLIST_DB_PATH, timeout=5.0)
        cursor = conn.execute(
            "SELECT source_message_id FROM worklist_items WHERE accession_number = ?",
            (accession_number,)
        )
        row = cursor.fetchone()
        conn.close()

        if row:
            logger.debug(f"Found action_id for accession {accession_number}: {row[0]}")
            return row[0]
        else:
            logger.debug(f"No action_id found for accession {accession_number}")
            return None
    except Exception as e:
        logger.warning(f"Could not look up action_id for accession {accession_number}: {e}")
        return None


def build_image_received_message(
    instance: dict,
    thumbnail_b64: Optional[str],
    action_id: Optional[str]
) -> dict:
    """
    Build image_received message matching the schema in example_image_received_message.json.

    Args:
        instance: Dictionary of instance metadata from database
        thumbnail_b64: Base64 encoded thumbnail, or None if not available
        action_id: Optional action_id to link back to originating worklist action

    Returns:
        Dictionary containing the complete message structure
    """
    message = {
        "schema_version": 1,
        "message_id": str(uuid.uuid4()),
        "message_type": "study.image_received",
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_system": "gateway-pacs",
        "source_reference": {
            "action_id": action_id
        },
        "parameters": {
            "participant": {
                "nhs_number": instance.get("patient_id"),
                "patient_name": instance.get("patient_name")
            },
            "study": {
                "accession_number": instance.get("accession_number"),
                "study_instance_uid": instance.get("study_instance_uid"),
                "modality": instance.get("modality"),
                "study_date": instance.get("study_date"),
                "study_time": instance.get("study_time"),
                "study_description": instance.get("study_description")
            },
            "series": {
                "series_instance_uid": instance.get("series_instance_uid"),
                "series_number": instance.get("series_number"),
                "series_description": instance.get("series_description")
            },
            "image": {
                "sop_instance_uid": instance.get("sop_instance_uid"),
                "instance_number": instance.get("instance_number"),
                "dimensions": {
                    "rows": instance.get("rows"),
                    "columns": instance.get("columns")
                },
                "acquisition": {
                    "view_position": instance.get("view_position"),
                    "laterality": instance.get("laterality")
                },
                "received_at": instance.get("received_at")
            }
        }
    }

    # Add thumbnail if available
    if thumbnail_b64:
        message["parameters"]["image"]["thumbnail"] = {
            "data": thumbnail_b64,
            "format": "jpeg"
        }

    return message


def send_image_message(message: dict) -> bool:
    """
    Send image_received message via Azure Relay to manage-screening.

    Args:
        message: The image_received message dictionary

    Returns:
        True if sent successfully, False otherwise
    """
    try:
        return send_image_event_sync(message)
    except Exception as e:
        logger.error(f"Error sending image message: {e}")
        return False


def process_pending_images():
    """Process a batch of pending images."""
    pending = get_pending_images()

    if not pending:
        return 0

    logger.info(f"Found {len(pending)} images pending processing")

    for instance in pending:
        if shutdown_requested:
            logger.info("Shutdown requested, stopping image processing")
            break

        sop_instance_uid = instance["sop_instance_uid"]
        storage_path = instance["storage_path"]
        dicom_path = PACS_STORAGE_ROOT / storage_path

        logger.info(f"Processing image {sop_instance_uid}")

        try:
            # Check if DICOM file exists
            if not dicom_path.exists():
                error = f"DICOM file not found: {dicom_path}"
                logger.error(error)
                mark_image_failed(sop_instance_uid, error)
                continue

            # Generate thumbnail
            thumbnail_path = generate_thumbnail(
                dicom_path=dicom_path,
                thumbnail_root=THUMBNAIL_ROOT,
                sop_instance_uid=sop_instance_uid,
                quality=THUMBNAIL_QUALITY,
                height=THUMBNAIL_HEIGHT,
            )

            # Encode thumbnail to base64
            thumbnail_b64 = None
            thumbnail_dims = (0, 0)
            if thumbnail_path and thumbnail_path.exists():
                thumbnail_b64 = encode_thumbnail_base64(thumbnail_path)
                thumbnail_dims = get_thumbnail_dimensions(thumbnail_path)
                logger.info(f"Generated thumbnail: {thumbnail_path} ({thumbnail_dims[0]}x{thumbnail_dims[1]})")
            else:
                logger.warning(f"Thumbnail generation failed for {sop_instance_uid}")

            # Look up action_id from worklist to link back to original action
            action_id = get_action_id_for_accession(instance.get("accession_number"))

            # Build the message
            message = build_image_received_message(
                instance=instance,
                thumbnail_b64=thumbnail_b64,
                thumbnail_dims=thumbnail_dims,
                action_id=action_id
            )

            # Send the message
            if send_image_message(message):
                mark_image_processed(sop_instance_uid)
                logger.info(f"Successfully processed image: {sop_instance_uid}")
            else:
                error = "Failed to send image message"
                mark_image_failed(sop_instance_uid, error)

        except Exception as e:
            error = f"Unexpected error: {str(e)}"
            logger.error(f"Error processing image {sop_instance_uid}: {e}", exc_info=True)
            mark_image_failed(sop_instance_uid, error)

    return len(pending)


def run_listener():
    """Main listener loop."""
    logger.info("=" * 60)
    logger.info("Starting Image Listener Service")
    logger.info("=" * 60)
    logger.info(f"Database: {PACS_DB_PATH}")
    logger.info(f"Storage: {PACS_STORAGE_ROOT}")
    logger.info(f"Thumbnails: {THUMBNAIL_ROOT}")
    logger.info(f"Poll interval: {POLL_INTERVAL}s")
    logger.info(f"Batch size: {BATCH_SIZE}")
    logger.info(f"Thumbnail quality: {THUMBNAIL_QUALITY}")
    logger.info(f"Thumbnail height: {THUMBNAIL_HEIGHT}px")
    logger.info("=" * 60)

    # Ensure thumbnail directory exists
    THUMBNAIL_ROOT.mkdir(parents=True, exist_ok=True)

    while not shutdown_requested:
        try:
            process_pending_images()
            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            time.sleep(POLL_INTERVAL)

    logger.info("Image listener service stopped")


if __name__ == "__main__":
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        run_listener()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
