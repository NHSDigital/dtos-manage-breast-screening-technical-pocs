# DICOM Modality Worklist Server with MPPS Support
#
# This script implements a DICOM worklist server with Modality Performed Procedure Step (MPPS)
# support for Orthanc. As of Orthanc v1.12.4, MPPS is not natively supported, so this script
# provides an independent worklist server using pydicom and pynetdicom.
#
# Configuration (in orthanc.json):
# - "MPPSAet": the AET of this worklist server (default: "ORTHANC_MWL")
# - "DicomPortMPPS": the port to be used (must be different from Orthanc DicomPort, default: 4243)

from pydicom.dataset import Dataset
import datetime
import json
import orthanc
import pynetdicom
import sys

from pynetdicom import AE, evt
from pynetdicom.sop_class import ModalityPerformedProcedureStep
from pynetdicom.sop_class import ModalityWorklistInformationFind
from pynetdicom.sop_class import Verification
from pydicom.uid import generate_uid

# Import the worklist storage layer
sys.path.insert(0, '/scripts')
from worklist_storage import WorklistStorage

worklist_server = None
managed_instances = {}
storage = None  # Will be initialized when Orthanc starts

def handle_find(event):
    """Handle a C-FIND request event for worklist queries."""
    try:
        ds = event.identifier
        orthanc.LogWarning(f"Received C-FIND request with identifier: {ds}")
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
        orthanc.LogWarning(f"Error in handle_find: {str(e)}")
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

        orthanc.LogWarning(f"MPPS N-CREATE: Started procedure for Accession={accession_number}, "
                          f"Study={study_instance_uid}, Modality={modality}")

        # Update database to record that this study acquisition has been started
        if storage and accession_number != 'UNKNOWN':
            updated = storage.update_status(accession_number, 'IN_PROGRESS', ds.SOPInstanceUID)
            if updated:
                orthanc.LogWarning(f"Database updated: {accession_number} -> IN_PROGRESS")
            else:
                orthanc.LogWarning(f"Warning: Could not find accession {accession_number} in database")

    except Exception as e:
        orthanc.LogWarning(f"Error in handle_create: {str(e)}")
        import traceback
        orthanc.LogWarning(f"Traceback: {traceback.format_exc()}")
        return 0x0110, None

    # Success - return the created dataset
    orthanc.LogWarning(f"MPPS N-CREATE successful, returning dataset")
    return 0x0000, ds

def handle_set(event):
    """Handle N-SET request for MPPS (completion/discontinuation of procedure)."""
    try:
        req = event.request
        orthanc.LogWarning(f"MPPS N-SET: Received request for SOP Instance UID: {req.RequestedSOPInstanceUID}")

        if req.RequestedSOPInstanceUID not in managed_instances:
            # Failure - SOP Instance not recognised
            orthanc.LogWarning(f"MPPS N-SET: SOP Instance UID not found in managed instances")
            return 0x0112, None

        ds = managed_instances[req.RequestedSOPInstanceUID]

        # The N-SET request's *Modification List* dataset
        mod_list = event.attribute_list

        status = mod_list.get('PerformedProcedureStepStatus', 'UNKNOWN')
        orthanc.LogWarning(f"MPPS N-SET: Updating procedure status to {status}")

        # Update database to record the procedure status change
        if storage and hasattr(ds, 'ScheduledStepAttributesSequence') and len(ds.ScheduledStepAttributesSequence) > 0:
            sps = ds.ScheduledStepAttributesSequence[0]
            accession_number = sps.get('AccessionNumber', 'UNKNOWN')
            if accession_number != 'UNKNOWN':
                updated = storage.update_status(accession_number, status)
                if updated:
                    orthanc.LogWarning(f"Database updated: {accession_number} -> {status}")
                else:
                    orthanc.LogWarning(f"Warning: Could not find accession {accession_number} in database")

        ds.update(mod_list)

        orthanc.LogWarning(f"MPPS N-SET successful")
        # Return status, dataset
        return 0x0000, ds
    except Exception as e:
        orthanc.LogWarning(f"Error in handle_set: {str(e)}")
        import traceback
        orthanc.LogWarning(f"Traceback: {traceback.format_exc()}")
        return 0x0110, None

def find_worklist(requestedDS):
    """Query worklist items based on the request."""
    worklist_objects = []

    # Extract search criteria from request
    sps_date = requestedDS.ScheduledProcedureStepSequence[0].ScheduledProcedureStepStartDate if hasattr(requestedDS, 'ScheduledProcedureStepSequence') else ""
    sps_modality = requestedDS.ScheduledProcedureStepSequence[0].Modality if hasattr(requestedDS, 'ScheduledProcedureStepSequence') else ""

    orthanc.LogWarning(f"Worklist query for Modality={sps_modality}, Date={sps_date}")

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
        orthanc.LogWarning(f"Database returned {len(worklist_items)} worklist items")
    else:
        orthanc.LogWarning("Warning: Storage not initialized, returning empty worklist")
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

    orthanc.LogWarning(f"Returning {len(worklist_objects)} worklist items")
    return worklist_objects

def handle_echo(event):
    """Handle a C-ECHO request event (DICOM ping)."""
    return 0x0000

def OnChange(changeType, level, resourceId):
    """Orthanc callback for change events."""
    global worklist_server, storage

    try:
        # Start the worklist server when Orthanc starts
        if changeType == orthanc.ChangeType.ORTHANC_STARTED:

            # Initialize the database storage
            orthanc.LogWarning('Initializing worklist database storage...')
            storage = WorklistStorage()
            stats = storage.get_statistics()
            orthanc.LogWarning(f'Database statistics: {stats}')

            # Get configuration from Orthanc config file
            config = json.loads(orthanc.GetConfiguration())
            mpps_aet = config.get('MPPSAet', "ORTHANC_MWL")
            mpps_port = config.get('DicomPortMPPS', 4243)

            orthanc.LogWarning(f'Starting Worklist server with AET={mpps_aet} on port {mpps_port}')

            # Create the Application Entity with the custom AE title
            ae = pynetdicom.AE(ae_title=mpps_aet)
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

            # Start the server
            worklist_server = ae.start_server(
                ('0.0.0.0', mpps_port),
                block=False,
                evt_handlers=handlers
            )

            orthanc.LogWarning('Worklist server using pynetdicom has started successfully')

        elif changeType == orthanc.ChangeType.ORTHANC_STOPPED:
            orthanc.LogWarning('Stopping pynetdicom Worklist server')
            if worklist_server:
                worklist_server.shutdown()
            if storage:
                storage.close()
                orthanc.LogWarning('Database storage closed')

    except Exception as e:
        orthanc.LogWarning(f"Error in OnChange: {str(e)}")

# Register the callback with Orthanc
orthanc.RegisterOnChangeCallback(OnChange)
