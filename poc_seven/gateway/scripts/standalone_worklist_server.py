#!/usr/bin/env python3
"""
Standalone DICOM Modality Worklist Server with MPPS Support

This script implements a DICOM worklist server with Modality Performed Procedure Step (MPPS)
support as a standalone Python application using pydicom and pynetdicom.

Configuration via environment variables:
- WORKLIST_AET: the AET of this worklist server (default: "ORTHANC_MWL")
- WORKLIST_PORT: the port to be used (default: 4243)
- WORKLIST_DB_PATH: path to SQLite database (default: "/var/lib/worklist/worklist.db")
- LOG_LEVEL: logging level (default: "INFO")
"""

from pydicom.dataset import Dataset
import datetime
import json
import logging
import os
import sys
from pynetdicom import AE, evt
from pynetdicom.sop_class import ModalityPerformedProcedureStep
from pynetdicom.sop_class import ModalityWorklistInformationFind
from pynetdicom.sop_class import Verification
from pydicom.uid import generate_uid

# Import the worklist storage layer
sys.path.insert(0, '/scripts')
from worklist_storage import WorklistStorage
from relay_event_sender import send_mpps_event_sync

# Global state
worklist_server = None
managed_instances = {}
storage = None

# Setup logging
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('worklist_server')


def handle_find(event):
    """Handle a C-FIND request event for worklist queries."""
    try:
        ds = event.identifier
        logger.info(f"Received C-FIND request with identifier: {ds}")
        dsArray = find_worklist(ds)

        # Return stored worklist items
        for instance in dsArray:
            # Check if C-CANCEL has been received
            if event.is_cancelled:
                yield (0xFE00, None)
                return
            # Pending - return this worklist item
            yield (0xFF00, instance)

        # Success - no more datasets
        yield 0x0000, None
    except Exception as e:
        logger.error(f"Error in handle_find: {str(e)}", exc_info=True)
        # Return failure status
        yield 0xA700, None  # Failure: Out of Resources


def handle_create(event):
    """Handle N-CREATE request for MPPS (start of procedure)."""
    ds = Dataset()
    try:
        req = event.request
        if req.AffectedSOPInstanceUID is None:
            # Failed - invalid attribute value
            return 0x0106, None

        # Can't create a duplicate SOP Instance
        if req.AffectedSOPInstanceUID in managed_instances:
            # Failed - duplicate SOP Instance
            return 0x0111, None

        # The N-CREATE request's *Attribute List* dataset
        attr_list = event.attribute_list

        # Performed Procedure Step Status must be 'IN PROGRESS'
        if "PerformedProcedureStepStatus" not in attr_list:
            # Failed - missing attribute
            return 0x0120, None

        if attr_list.PerformedProcedureStepStatus.upper() != 'IN PROGRESS':
            return 0x0106, None

        # Add the SOP Common module elements
        ds.SOPClassUID = ModalityPerformedProcedureStep
        ds.SOPInstanceUID = req.AffectedSOPInstanceUID

        # Update with the requested attributes
        ds.update(attr_list)

        # Add the dataset to the managed SOP Instances
        managed_instances[ds.SOPInstanceUID] = ds

        # Extract attributes with error checking
        modality = attr_list.get('Modality', 'UNKNOWN')
        accession_number = 'UNKNOWN'
        study_instance_uid = 'UNKNOWN'

        if hasattr(attr_list, 'ScheduledStepAttributesSequence') and len(attr_list.ScheduledStepAttributesSequence) > 0:
            sps = attr_list.ScheduledStepAttributesSequence[0]
            accession_number = sps.get('AccessionNumber', 'UNKNOWN')
            study_instance_uid = sps.get('StudyInstanceUID', 'UNKNOWN')

        logger.info(f"MPPS N-CREATE: Started procedure for Accession={accession_number}, "
                   f"Study={study_instance_uid}, Modality={modality}")

        # Update database to record that this study acquisition has been started
        if storage and accession_number != 'UNKNOWN':
            source_message_id = storage.update_status(accession_number, 'IN_PROGRESS', ds.SOPInstanceUID)
            if source_message_id:
                logger.info(f"Database updated: {accession_number} -> IN_PROGRESS")
                # Send MPPS event back to Django via relay
                send_mpps_event_sync(
                    action_id=source_message_id,
                    accession_number=accession_number,
                    status='IN PROGRESS',
                    mpps_instance_uid=ds.SOPInstanceUID
                )
            else:
                logger.warning(f"Could not find accession {accession_number} in database")

    except Exception as e:
        logger.error(f"Error in handle_create: {str(e)}", exc_info=True)
        return 0x0110, None

    # Success - return the created dataset
    logger.info(f"MPPS N-CREATE successful, returning dataset")
    return 0x0000, ds


def handle_set(event):
    """Handle N-SET request for MPPS (completion/discontinuation of procedure)."""
    try:
        req = event.request
        logger.info(f"MPPS N-SET: Received request for SOP Instance UID: {req.RequestedSOPInstanceUID}")

        if req.RequestedSOPInstanceUID not in managed_instances:
            # Failure - SOP Instance not recognised
            logger.warning(f"MPPS N-SET: SOP Instance UID not found in managed instances")
            return 0x0112, None

        ds = managed_instances[req.RequestedSOPInstanceUID]

        # The N-SET request's *Modification List* dataset
        mod_list = event.attribute_list

        status = mod_list.get('PerformedProcedureStepStatus', 'UNKNOWN')
        logger.info(f"MPPS N-SET: Updating procedure status to {status}")

        # Update database to record the procedure status change
        if storage and hasattr(ds, 'ScheduledStepAttributesSequence') and len(ds.ScheduledStepAttributesSequence) > 0:
            sps = ds.ScheduledStepAttributesSequence[0]
            accession_number = sps.get('AccessionNumber', 'UNKNOWN')
            if accession_number != 'UNKNOWN':
                source_message_id = storage.update_status(accession_number, status)
                if source_message_id:
                    logger.info(f"Database updated: {accession_number} -> {status}")
                    # Send MPPS event back to Django via relay
                    send_mpps_event_sync(
                        action_id=source_message_id,
                        accession_number=accession_number,
                        status=status,
                        mpps_instance_uid=req.RequestedSOPInstanceUID
                    )
                else:
                    logger.warning(f"Could not find accession {accession_number} in database")

        ds.update(mod_list)

        logger.info(f"MPPS N-SET successful")
        # Return status, dataset
        return 0x0000, ds
    except Exception as e:
        logger.error(f"Error in handle_set: {str(e)}", exc_info=True)
        return 0x0110, None


def find_worklist(requestedDS):
    """Query worklist items based on the request."""
    worklist_objects = []

    # Extract search criteria from request
    sps_date = requestedDS.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate if hasattr(requestedDS, 'ScheduledProcedureStepSequence') else ""
    sps_modality = requestedDS.ScheduledProcedureStepSequence[0].Modality if hasattr(requestedDS, 'ScheduledProcedureStepSequence') else ""

    logger.info(f"Worklist query for Modality={sps_modality}, Date={sps_date}")

    # Query database for worklist items
    if storage:
        # Build query parameters - only filter if values are provided (not empty or wildcard)
        query_params = {}

        if sps_modality and sps_modality != '*':
            query_params['modality'] = sps_modality

        if sps_date and sps_date != '*':
            query_params['scheduled_date'] = sps_date

        # Query the database
        worklist_items = storage.find_worklist_items(**query_params)
        logger.info(f"Database returned {len(worklist_items)} worklist items")
    else:
        logger.warning("Storage not initialized, returning empty worklist")
        worklist_items = []

    for item in worklist_items:
        ds = Dataset()
        ds.is_little_endian = True
        ds.is_implicit_VR = True

        # Patient identification module
        ds.PatientName = item["patient_name"]
        ds.PatientID = item["patient_id"]
        ds.SpecificCharacterSet = "ISO_IR 192"
        ds.PatientBirthDate = item["patient_birth_date"]
        ds.PatientSex = item["patient_sex"] if item["patient_sex"] else ""

        # Create the scheduled procedure step sequence
        sps = Dataset()
        sps.Modality = item["modality"]
        sps.ScheduledStationAETitle = ""
        sps.ScheduledProcedureStepStartDate = item["scheduled_date"]
        sps.ScheduledProcedureStepStartTime = item["scheduled_time"]
        sps.ScheduledPerformingPhysicianName = ""
        sps.ScheduledProcedureStepDescription = item["study_description"] if item["study_description"] else ""
        sps.ScheduledProcedureStepID = item["accession_number"]

        # Add the Scheduled Procedure Step Sequence to the dataset
        ds.ScheduledProcedureStepSequence = [sps]

        # Study module
        ds.AccessionNumber = item["accession_number"]
        # Use existing study UID if present, otherwise generate a new one
        ds.StudyInstanceUID = item["study_instance_uid"] if item["study_instance_uid"] else generate_uid()
        ds.StudyID = item["accession_number"]
        ds.RequestedProcedureDescription = item["study_description"] if item["study_description"] else ""
        ds.RequestedProcedureID = item["accession_number"]

        worklist_objects.append(ds)

    logger.info(f"Returning {len(worklist_objects)} worklist items")
    return worklist_objects


def handle_echo(event):
    """Handle a C-ECHO request event (DICOM ping)."""
    return 0x0000


def start_server():
    """Initialize and start the worklist server."""
    global worklist_server, storage

    # Get configuration from environment variables
    worklist_aet = os.getenv('WORKLIST_AET', 'ORTHANC_MWL')
    worklist_port = int(os.getenv('WORKLIST_PORT', '4243'))
    db_path = os.getenv('WORKLIST_DB_PATH', '/var/lib/worklist/worklist.db')

    logger.info('='*60)
    logger.info('Starting Standalone DICOM Modality Worklist Server')
    logger.info('='*60)

    # Initialize the database storage
    logger.info(f'Initializing worklist database storage at {db_path}...')
    storage = WorklistStorage(db_path=db_path)
    stats = storage.get_statistics()
    logger.info(f'Database statistics: {stats}')

    logger.info(f'Starting Worklist server with AET={worklist_aet} on port {worklist_port}')

    # Create the Application Entity with the custom AE title
    ae = AE(ae_title=worklist_aet)
    ae.add_supported_context(ModalityPerformedProcedureStep)
    ae.add_supported_context(ModalityWorklistInformationFind)
    ae.add_supported_context(Verification)

    # Set up event handlers
    handlers = [
        (evt.EVT_N_CREATE, handle_create),
        (evt.EVT_N_SET, handle_set),
        (evt.EVT_C_FIND, handle_find),
        (evt.EVT_C_ECHO, handle_echo)
    ]

    # Start the server (blocking)
    logger.info('Starting pynetdicom server...')
    worklist_server = ae.start_server(
        ('0.0.0.0', worklist_port),
        block=True,
        evt_handlers=handlers
    )

    logger.info('Worklist server has started successfully')


def shutdown_server():
    """Shutdown the worklist server gracefully."""
    logger.info('Shutting down worklist server...')
    if worklist_server:
        worklist_server.shutdown()
    if storage:
        storage.close()
        logger.info('Database storage closed')


if __name__ == '__main__':
    import signal

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
