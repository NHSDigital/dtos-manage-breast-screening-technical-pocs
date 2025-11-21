from gateway.models import GatewayAction
import uuid
from datetime import datetime, timezone
from provider.models import AppointmentState


class CreateWorklistItemCreateAction:
    def __init__(self, appointment, gateway):
        self.gateway = gateway
        self.appointment = appointment
        self.participant = appointment.participant

    @classmethod
    def call(cls, appointment, gateway):
        return cls(appointment, gateway).execute()

    def execute(self):
        action_id = uuid.uuid4()
        accession_number = self._generate_accession_number()

        # Update appointment state to be visible on the page
        # The action is persisted locally for now (sending to gateway will be a future step)
        self.appointment.state = AppointmentState.SENT_TO_MODALITY.value
        self.appointment.save(update_fields=["state"])

        # Create the gateway action in the database
        action = GatewayAction.objects.create(
            id=action_id,
            gateway=self.gateway,
            type=GatewayAction.TYPE_WORKLIST_ADD,
            payload=self.generate_payload(
                action_id=action_id,
                accession_number=accession_number,
            ),
        )

        # Action is persisted locally - sending to gateway will be implemented in a future step

        return action

    def _generate_accession_number(self):
        """Generate an accession number for the worklist item"""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        random_suffix = uuid.uuid4().hex[:4].upper()
        return f"ACC-{timestamp}-{random_suffix}"

    def generate_payload(self, action_id, accession_number):
        """Generate the gateway action payload in MWL format"""

        # Format participant name as DICOM PN (Patient Name): LAST^FIRST
        participant_name = f"{self.participant.last_name.upper()}^{self.participant.first_name.upper()}"

        # Format dates in DICOM format (YYYYMMDD)
        birth_date = self.participant.date_of_birth.strftime("%Y%m%d")

        # Get appointment date and time from clinic slot
        appointment_date = self.appointment.clinic_slot.clinic.date.strftime("%Y%m%d")
        appointment_time = self.appointment.clinic_slot.start_time.strftime("%H%M%S")

        # Generate requested procedure ID
        requested_procedure_id = f"REQ-{datetime.now(timezone.utc).strftime('%Y%m%d')}-{uuid.uuid4().hex[:4].upper()}"

        payload = {
            "schema_version": 1,
            "action_id": str(action_id),
            "action_type": "worklist.create_item",
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "source_system": "manage-breast-screening",
            "source_reference": {
                "appointment_id": str(self.appointment.id),
                "participant_id": self.participant.nhs_number,
            },
            "parameters": {
                "worklist_item": {
                    "accession_number": accession_number,
                    "requested_procedure_id": requested_procedure_id,
                    "participant": {
                        "nhs_number": self.participant.nhs_number,
                        "name": participant_name,
                        "birth_date": birth_date,
                        "sex": "F",
                    },
                    "scheduled": {"date": appointment_date, "time": appointment_time},
                    "procedure": {
                        "modality": "MG",
                        "station_name": "MMG_ROOM_1",
                        "study_description": "Screening Mammography",
                    },
                }
            },
        }

        return payload
