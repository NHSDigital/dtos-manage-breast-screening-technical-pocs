#!/usr/bin/env python3
"""
Thumbnail Generator Service

Polls the PACS database for instances that need thumbnails and generates them.
Runs as a separate service to avoid blocking PACS C-STORE operations.
"""

import logging
import os
import signal
import sqlite3
import sys
import time
from contextlib import contextmanager
from pathlib import Path

from thumbnail_generator import generate_thumbnail

# Setup logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("thumbnail_watcher")

# Configuration
PACS_DB_PATH = os.getenv("PACS_DB_PATH", "/var/lib/pacs/pacs.db")
PACS_STORAGE_ROOT = Path(os.getenv("PACS_STORAGE_ROOT", "/var/lib/pacs/storage"))
THUMBNAIL_ROOT = Path(os.getenv("THUMBNAIL_ROOT", "/var/lib/pacs/thumbnails"))
POLL_INTERVAL = int(os.getenv("THUMBNAIL_POLL_INTERVAL", "5"))  # seconds
BATCH_SIZE = int(os.getenv("THUMBNAIL_BATCH_SIZE", "10"))
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


def get_pending_thumbnails(limit=BATCH_SIZE):
    """
    Get instances that need thumbnail generation.

    Returns list of dicts with: sop_instance_uid, storage_path
    """
    with get_db_connection() as conn:
        cursor = conn.execute(
            """
            SELECT sop_instance_uid, storage_path
            FROM stored_instances
            WHERE thumbnail_status = 'PENDING'
              AND status = 'STORED'
            ORDER BY received_at ASC
            LIMIT ?
            """,
            (limit,),
        )
        return [dict(row) for row in cursor.fetchall()]


def mark_thumbnail_generated(sop_instance_uid: str):
    """Mark thumbnail as successfully generated."""
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
    logger.info(f"Marked thumbnail as generated: {sop_instance_uid}")


def mark_thumbnail_failed(sop_instance_uid: str, error: str):
    """Mark thumbnail generation as failed."""
    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE stored_instances
            SET thumbnail_status = 'FAILED',
                thumbnail_error = ?
            WHERE sop_instance_uid = ?
            """,
            (error[:500], sop_instance_uid),  # Limit error message length
        )
        conn.commit()
    logger.warning(f"Marked thumbnail as failed: {sop_instance_uid} - {error}")


def process_pending_thumbnails():
    """Process a batch of pending thumbnails."""
    pending = get_pending_thumbnails()

    if not pending:
        return 0

    logger.info(f"Found {len(pending)} instances pending thumbnail generation")

    for instance in pending:
        if shutdown_requested:
            logger.info("Shutdown requested, stopping thumbnail processing")
            break

        sop_instance_uid = instance["sop_instance_uid"]
        storage_path = instance["storage_path"]
        dicom_path = PACS_STORAGE_ROOT / storage_path

        logger.info(f"Generating thumbnail for {sop_instance_uid}")

        try:
            # Check if DICOM file exists
            if not dicom_path.exists():
                error = f"DICOM file not found: {dicom_path}"
                logger.error(error)
                mark_thumbnail_failed(sop_instance_uid, error)
                continue

            # Generate thumbnail
            thumbnail_path = generate_thumbnail(
                dicom_path=dicom_path,
                thumbnail_root=THUMBNAIL_ROOT,
                sop_instance_uid=sop_instance_uid,
                quality=THUMBNAIL_QUALITY,
                height=THUMBNAIL_HEIGHT,
            )

            if thumbnail_path:
                mark_thumbnail_generated(sop_instance_uid)
                logger.info(f"Successfully generated thumbnail: {thumbnail_path}")
            else:
                error = "Thumbnail generation failed (no thumbnail created)"
                mark_thumbnail_failed(sop_instance_uid, error)

        except Exception as e:
            error = f"Unexpected error: {str(e)}"
            logger.error(f"Error generating thumbnail for {sop_instance_uid}: {e}", exc_info=True)
            mark_thumbnail_failed(sop_instance_uid, error)

    return len(pending)


def run_watcher():
    """Main watcher loop."""
    logger.info("=" * 60)
    logger.info("Starting Thumbnail Generator Service")
    logger.info("=" * 60)
    logger.info(f"Database: {PACS_DB_PATH}")
    logger.info(f"Storage: {PACS_STORAGE_ROOT}")
    logger.info(f"Thumbnails: {THUMBNAIL_ROOT}")
    logger.info(f"Poll interval: {POLL_INTERVAL}s")
    logger.info(f"Batch size: {BATCH_SIZE}")
    logger.info(f"Quality: {THUMBNAIL_QUALITY}")
    logger.info(f"Height: {THUMBNAIL_HEIGHT}px")
    logger.info("=" * 60)

    # Ensure thumbnail directory exists
    THUMBNAIL_ROOT.mkdir(parents=True, exist_ok=True)

    consecutive_empty_polls = 0

    while not shutdown_requested:
        try:
            processed = process_pending_thumbnails()

            if processed == 0:
                consecutive_empty_polls += 1
                # Gradually increase sleep time when idle, up to POLL_INTERVAL
                sleep_time = min(consecutive_empty_polls * 1, POLL_INTERVAL)
                time.sleep(sleep_time)
            else:
                consecutive_empty_polls = 0
                # Short sleep between batches when busy
                time.sleep(0.5)

        except KeyboardInterrupt:
            logger.info("Keyboard interrupt received")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            time.sleep(POLL_INTERVAL)

    logger.info("Thumbnail generator service stopped")


if __name__ == "__main__":
    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        run_watcher()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
