from gateway.models import Message

class CreateScreeningOrderGatewayMessage:
    def __init__(self, participant, gateway):
        self.gateway = gateway
        self.participant = participant

    def execute(self):
        return GatewayMessage.objects.create(
                id = uuid.uuid4(),
                gateway = self.gateway,
                participant = self.participant,
                type = Message.TYPE_FHIR,
                destination = self.gateway.order_url,
                payload = fhir_payload(message_id = self.id),
        )

    def fhir_payload(self, message_id):
        # This hasn't been validated and has been generated for a demo only

        fhir_request = {
                "resourceType": "ServiceRequest",
                "id": message_id,
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
                    "reference": f"Patient/{self.participant.nhs_number}",
                    "identifier": {
                        "system": "https://fhir.nhs.uk/Id/nhs-number",
                        "value": self.participant.nhs_number
                        },
                    "display": f"Patient with NHS Number {nhs_number}"
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
