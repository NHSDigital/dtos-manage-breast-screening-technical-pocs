#!/usr/bin/env python3
"""
Standalone DICOM PACS Server (Application Entity)

This script implements a simple PACS server that supports:
- C-ECHO: DICOM verification (ping)
- C-STORE: Receiving and storing DICOM images with hash-based storage

Configuration via environment variables:
- PACS_AET: the AET of this PACS server (default: "SCREENING_PACS")
- PACS_PORT: the port to be used (default: 4244)
- PACS_STORAGE_PATH: path to store DICOM files (default: "/var/lib/pacs/storage")
- PACS_DB_PATH: path to PACS database (default: "/var/lib/pacs/pacs.db")
- LOG_LEVEL: logging level (default: "INFO")
"""

import logging
import os
import sys
import signal
from io import BytesIO
from pathlib import Path
from pydicom import dcmread
from pydicom.dataset import Dataset
from pynetdicom import AE, evt, StoragePresentationContexts
from pynetdicom.sop_class import Verification

# Import PACS storage layer
sys.path.insert(0, '/scripts')
from pacs_storage import PACSStorage

# Setup logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('pacs_server')

# Global state
pacs_server = None
storage = None


def handle_store(event):
    """
    Handle a C-STORE request event.

    Stores the received DICOM dataset using hash-based storage and database indexing.
    """
    try:
        # Get the dataset from the event
        ds = event.dataset
        ds.file_meta = event.file_meta

        # Extract metadata
        sop_instance_uid = str(getattr(ds, 'SOPInstanceUID', ''))

        if not sop_instance_uid:
            logger.error("Missing SOP Instance UID")
            return 0xC000  # Failure

        # Get calling AE title
        source_aet = event.assoc.requestor.ae_title.decode('utf-8') if hasattr(event.assoc.requestor.ae_title, 'decode') else str(event.assoc.requestor.ae_title)

        # Serialize dataset to bytes
        buffer = BytesIO()
        ds.save_as(buffer, write_like_original=False)
        file_data = buffer.getvalue()

        # Extract metadata for database
        metadata = {
            'patient_id': str(getattr(ds, 'PatientID', '')),
            'patient_name': str(getattr(ds, 'PatientName', '')),
            'study_instance_uid': str(getattr(ds, 'StudyInstanceUID', '')),
            'series_instance_uid': str(getattr(ds, 'SeriesInstanceUID', '')),
            'accession_number': str(getattr(ds, 'AccessionNumber', '')),
            'study_date': str(getattr(ds, 'StudyDate', '')),
            'study_time': str(getattr(ds, 'StudyTime', '')),
            'study_description': str(getattr(ds, 'StudyDescription', '')),
            'series_number': str(getattr(ds, 'SeriesNumber', '')),
            'series_description': str(getattr(ds, 'SeriesDescription', '')),
            'modality': str(getattr(ds, 'Modality', '')),
            'instance_number': str(getattr(ds, 'InstanceNumber', '')),
            'view_position': str(getattr(ds, 'ViewPosition', '')),
            'laterality': str(getattr(ds, 'ImageLaterality', '') or getattr(ds, 'Laterality', '')),
            'transfer_syntax_uid': str(getattr(ds.file_meta, 'TransferSyntaxUID', '')),
            'sop_class_uid': str(getattr(ds, 'SOPClassUID', '')),
            'rows': int(getattr(ds, 'Rows', 0)) if hasattr(ds, 'Rows') else None,
            'columns': int(getattr(ds, 'Columns', 0)) if hasattr(ds, 'Columns') else None,
            # Dose and exposure parameters
            'organ_dose': str(getattr(ds, 'OrganDose', '')) if hasattr(ds, 'OrganDose') else None,
            'entrance_dose_in_mgy': str(getattr(ds, 'EntranceDoseInmGy', '')) if hasattr(ds, 'EntranceDoseInmGy') else None,
            'kvp': str(getattr(ds, 'KVP', '')) if hasattr(ds, 'KVP') else None,
            'exposure_in_uas': str(getattr(ds, 'ExposureInuAs', '')) if hasattr(ds, 'ExposureInuAs') else None,
            'anode_target_material': str(getattr(ds, 'AnodeTargetMaterial', '')) if hasattr(ds, 'AnodeTargetMaterial') else None,
            'filter_material': str(getattr(ds, 'FilterMaterial', '')) if hasattr(ds, 'FilterMaterial') else None,
            'filter_thickness': str(getattr(ds, 'FilterThicknessMinimum', '')) if hasattr(ds, 'FilterThicknessMinimum') else None,
        }

        # Store using storage layer
        if storage:
            try:
                file_path = storage.store_instance(sop_instance_uid, file_data, metadata, source_aet)
                logger.info(f"Stored instance: {sop_instance_uid}")
                logger.info(f"  Patient: {metadata['patient_id']} - {metadata['patient_name']}")
                logger.info(f"  Study: {metadata['study_instance_uid']}")
                logger.info(f"  Modality: {metadata['modality']}")
                logger.info(f"  Accession: {metadata['accession_number']}")
                return 0x0000  # Success
            except ValueError as e:
                # Instance already exists
                logger.warning(f"Instance already exists: {sop_instance_uid}")
                return 0x0000  # Return success (idempotent)
        else:
            logger.error("Storage not initialized")
            return 0xC000  # Failure

    except Exception as e:
        logger.error(f"Error in handle_store: {str(e)}", exc_info=True)
        return 0xC000  # Failure: Unable to process


def handle_echo(event):
    """Handle a C-ECHO request event (DICOM ping)."""
    logger.info("Received C-ECHO request")
    return 0x0000


def start_server():
    """Initialize and start the PACS server."""
    global pacs_server, storage

    # Get configuration from environment variables
    pacs_aet = os.getenv('PACS_AET', 'SCREENING_PACS')
    pacs_port = int(os.getenv('PACS_PORT', '4244'))
    storage_dir = os.getenv('PACS_STORAGE_PATH', '/var/lib/pacs/storage')
    db_path = os.getenv('PACS_DB_PATH', '/var/lib/pacs/pacs.db')

    logger.info('='*60)
    logger.info('Starting Standalone DICOM PACS Server')
    logger.info('='*60)

    # Initialize storage layer
    logger.info(f'Initializing PACS storage...')
    logger.info(f'  Database: {db_path}')
    logger.info(f'  Storage: {storage_dir}')

    storage = PACSStorage(db_path=db_path, storage_root=storage_dir)

    # Get statistics
    stats = storage.get_statistics()
    logger.info(f'Storage statistics:')
    logger.info(f'  Instances: {stats.get("total_instances", 0)}')
    logger.info(f'  Studies: {stats.get("total_studies", 0)}')
    logger.info(f'  Patients: {stats.get("total_patients", 0)}')
    total_size = stats.get("total_size_bytes") or 0
    logger.info(f'  Total size: {total_size:,} bytes')

    logger.info(f'Starting PACS server with AET={pacs_aet} on port {pacs_port}')

    # Create the Application Entity
    ae = AE(ae_title=pacs_aet)

    # Add supported contexts for C-ECHO
    ae.add_supported_context(Verification)

    # Add supported contexts for C-STORE (all storage SOP classes)
    # StoragePresentationContexts includes all standard storage SOP classes
    for cx in StoragePresentationContexts:
        ae.add_supported_context(cx.abstract_syntax)

    # Set up event handlers
    handlers = [
        (evt.EVT_C_STORE, handle_store),
        (evt.EVT_C_ECHO, handle_echo)
    ]

    # Start the server (blocking)
    logger.info('Starting pynetdicom PACS server...')
    logger.info('Supported operations: C-ECHO, C-STORE')
    logger.info(f'Supported storage SOP classes: {len(StoragePresentationContexts)}')

    pacs_server = ae.start_server(
        ('0.0.0.0', pacs_port),
        block=True,
        evt_handlers=handlers
    )

    logger.info('PACS server has started successfully')


def shutdown_server():
    """Shutdown the PACS server gracefully."""
    logger.info('Shutting down PACS server...')
    if pacs_server:
        pacs_server.shutdown()
    if storage:
        storage.close()
    logger.info('PACS server stopped')


if __name__ == '__main__':
    def signal_handler(sig, frame):
        logger.info('Received shutdown signal')
        shutdown_server()
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        start_server()
    except Exception as e:
        logger.error(f'Fatal error: {str(e)}', exc_info=True)
        sys.exit(1)
