"""
Thumbnail Generator for DICOM Images

Generates JPEG thumbnails from DICOM files using dcm2img.
"""

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Optional

logger = logging.getLogger("thumbnail_generator")


def generate_thumbnail(
    dicom_path: Path,
    thumbnail_root: Path,
    sop_instance_uid: str,
    quality: int = 25,
    height: int = 188,
) -> Optional[Path]:
    """
    Generate a JPEG thumbnail from a DICOM file using dcm2img.

    Args:
        dicom_path: Path to the DICOM file
        thumbnail_root: Root directory for thumbnails
        sop_instance_uid: SOP Instance UID for consistent naming
        quality: JPEG quality (1-100, default: 25)
        height: Target height in pixels (default: 188)

    Returns:
        Path to generated thumbnail, or None if generation failed
    """
    try:
        # Compute thumbnail path using same hash structure as storage
        hash_hex = hashlib.sha256(sop_instance_uid.encode()).hexdigest()
        level1 = hash_hex[:2]
        level2 = hash_hex[2:4]
        filename = f"{hash_hex[:16]}.jpg"

        # Create directory structure
        thumbnail_dir = thumbnail_root / level1 / level2
        thumbnail_dir.mkdir(parents=True, exist_ok=True)

        thumbnail_path = thumbnail_dir / filename

        # Build dcm2img command
        # +oj: Output JPEG
        # +Jq <quality>: JPEG quality (1-100)
        # --min-max-window: Use min/max pixel values for windowing
        # --scale-y-size <height>: Scale height to specified size
        cmd = [
            "dcm2img",
            "+oj",  # Output JPEG format
            "+Jq",
            str(quality),  # JPEG quality
            "--min-max-window",  # Use min/max windowing
            "--scale-y-size",
            str(height),  # Scale to height
            str(dicom_path),  # Input DICOM file
            str(thumbnail_path),  # Output JPEG file
        ]

        logger.debug(f"Running: {' '.join(cmd)}")

        # Execute dcm2img
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

        if result.returncode != 0:
            logger.error(f"dcm2img failed: {result.stderr}")
            return None

        if thumbnail_path.exists():
            logger.info(
                f"Generated thumbnail: {thumbnail_path} ({thumbnail_path.stat().st_size} bytes)"
            )
            return thumbnail_path
        else:
            logger.error(f"Thumbnail not created: {thumbnail_path}")
            return None

    except subprocess.TimeoutExpired:
        logger.error(f"Thumbnail generation timed out for {dicom_path}")
        return None
    except Exception as e:
        logger.error(f"Error generating thumbnail: {e}", exc_info=True)
        return None


def get_thumbnail_path(thumbnail_root: Path, sop_instance_uid: str) -> Path:
    """
    Get the expected thumbnail path for a SOP Instance UID.

    Args:
        thumbnail_root: Root directory for thumbnails
        sop_instance_uid: SOP Instance UID

    Returns:
        Expected path to thumbnail (may not exist)
    """
    hash_hex = hashlib.sha256(sop_instance_uid.encode()).hexdigest()
    level1 = hash_hex[:2]
    level2 = hash_hex[2:4]
    filename = f"{hash_hex[:16]}.jpg"

    return thumbnail_root / level1 / level2 / filename
