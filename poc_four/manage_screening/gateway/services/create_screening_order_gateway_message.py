from gateway.models import Message
import uuid
from datetime import datetime
import json

class CreateScreeningOrderGatewayMessage:
    def __init__(self, participant, gateway):
        self.gateway = gateway
        self.participant = participant

    @classmethod
    def call(cls, participant, gateway):
        return cls(participant, gateway).execute()


    def execute(self):
        message_id = uuid.uuid4()
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
