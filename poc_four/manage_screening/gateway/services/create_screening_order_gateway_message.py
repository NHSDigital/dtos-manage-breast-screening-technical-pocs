from gateway.models import Message
import uuid
from datetime import datetime
import json
from provider.models import AppointmentState

class CreateScreeningOrderGatewayMessage:
    def __init__(self, appointment, gateway):
        self.gateway = gateway
        self.appointment = appointment
        self.participant = appointment.participant

    @classmethod
    def call(cls, appointment, gateway):
        return cls(appointment, gateway).execute()


    def execute(self):
        message_id = uuid.uuid4()

        # set this here as we want the state change to be visible on the page. The message
        # is sent asynchronously to the gateway
        self.appointment.state = AppointmentState.SENT_TO_MODALITY.value
        self.appointment.save(update_fields=["state"])

        return Message.objects.create(
                id = message_id,
                gateway = self.gateway,
                participant = self.participant,
                type = Message.TYPE_FHIR,
                destination = self.gateway.order_url,
                payload = self.fhir_payload(message_id = message_id)
        )
    
    def fhir_payload(self, message_id):
        # This hasn't been validated and has been generated for a demo only
        nhs_number = self.participant.nhs_number

        fhir_request = {
                "resourceType": "ServiceRequest",
                "id": str(message_id),
                "status": "active",
                "intent": "order",
                "category": [
                    {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/service-category",
                                "code": "imaging",
                                "display": "Imaging"
                                }
                            ]
                        }
                    ],
                "code": {
                    "coding": [
                        {
                            "system": "http://snomed.info/sct",
                            "code": "1224585002",
                            "display": "Screening mammography of breast"
                            }
                        ],
                    "text": "Mammogram"
                    },
                "subject": {
                    "reference": f"Patient/{nhs_number}",
                    "identifier": {
                        "system": "https://fhir.nhs.uk/Id/nhs-number",
                        "value": f"{nhs_number}"
                        },
                    "display": "Patient with NHS Number"
                    },
                "authoredOn": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "requester": {
                    "reference": "Organization/NSP",
                    "display": "National Screening Program"
                    },
                "performer": [
                    {
                        "reference": "Organization/example-hospital",
                        "display": "Example Radiology Center"
                        }
                    ],
                "reasonCode": [
                    {
                        "coding": [
                            {
                                "system": "http://snomed.info/sct",
                                "code": "395555000",
                                "display": "Screening procedure"
                                }
                            ]
                        }
                    ]
                 }

        return json.dumps(fhir_request, indent=4)
