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

from pynetdicom import AE, evt
from pynetdicom.sop_class import ModalityPerformedProcedureStep
from pynetdicom.sop_class import ModalityWorklistInformationFind
from pynetdicom.sop_class import Verification
from pydicom.uid import generate_uid

worklist_server = None
managed_instances = {}

# TODO-DB: Connect to your database
# For POC purposes, we'll use sample data below

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

        # TODO-DB: Update your DB to record that this study acquisition has been started

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

        # TODO-DB: Update your DB to record that this study acquisition is complete

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

    # TODO-DB: Query your database to get the planned exams for this modality and date
    # For POC purposes, we're using sample data
    today = datetime.datetime.now().strftime("%Y%m%d")
    appointments = [
        {
            "PatientID": "BS001234",
            "PatientName": "SMITH^JANE",
            "PatientBirthDate": "19650315",
            "PatientSex": "F",
            "AppointmentDate": today,
            "AppointmentTime": "100000",
            "AppointmentId": "ACC001",
            "StudyDescription": "Bilateral Mammography",
            "ProcedureCode": "MAMMO_BILATERAL"
        },
        {
            "PatientID": "BS005678",
            "PatientName": "JONES^MARY",
            "PatientBirthDate": "19700822",
            "PatientSex": "F",
            "AppointmentDate": today,
            "AppointmentTime": "110000",
            "AppointmentId": "ACC002",
            "StudyDescription": "Screening Mammography",
            "ProcedureCode": "MAMMO_SCREENING"
        }
    ]

    for a in appointments:
        ds = Dataset()
        ds.is_little_endian = True
        ds.is_implicit_VR = True

        # Patient identification module
        ds.PatientName = a["PatientName"]
        ds.PatientID = a["PatientID"]
        ds.SpecificCharacterSet = "ISO_IR 192"
        ds.PatientBirthDate = a["PatientBirthDate"]
        ds.PatientSex = a["PatientSex"]

        # Create the scheduled procedure step sequence
        sps = Dataset()
        sps.Modality = sps_modality if sps_modality else "MG"  # Default to MG (Mammography)
        sps.ScheduledStationAETitle = ""
        sps.ScheduledProcedureStepStartDate = a["AppointmentDate"]
        sps.ScheduledProcedureStepStartTime = a["AppointmentTime"]
        sps.ScheduledPerformingPhysicianName = ""
        sps.ScheduledProcedureStepDescription = a["StudyDescription"]
        sps.ScheduledProcedureStepID = a["AppointmentId"]

        # Add the Scheduled Procedure Step Sequence to the dataset
        ds.ScheduledProcedureStepSequence = [sps]

        # Study module
        ds.AccessionNumber = a["AppointmentId"]
        ds.StudyInstanceUID = generate_uid()
        ds.StudyID = a["AppointmentId"]
        ds.RequestedProcedureDescription = a["StudyDescription"]
        ds.RequestedProcedureID = a["AppointmentId"]

        worklist_objects.append(ds)

    orthanc.LogWarning(f"Returning {len(worklist_objects)} worklist items")
    return worklist_objects

def handle_echo(event):
    """Handle a C-ECHO request event (DICOM ping)."""
    return 0x0000

def OnChange(changeType, level, resourceId):
    """Orthanc callback for change events."""
    global worklist_server

    try:
        # Start the worklist server when Orthanc starts
        if changeType == orthanc.ChangeType.ORTHANC_STARTED:

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

    except Exception as e:
        orthanc.LogWarning(f"Error in OnChange: {str(e)}")

# Register the callback with Orthanc
orthanc.RegisterOnChangeCallback(OnChange)
