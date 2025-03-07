from django import forms
from gateway.models import Message, Gateway
from participant.models import Participant
from gateway.services.create_screening_order_gateway_message import CreateScreeningOrderGatewayMessage

class ScreeningOrderGatewayMessageForm(forms.Form):
    participant_id = forms.IntegerField(widget=forms.HiddenInput())
    gateway_id = forms.UUIDField(widget=forms.HiddenInput())

    def save(self):
        participant = Participant.objects.get(id=self.cleaned_data["participant_id"])
        gateway = Gateway.objects.get(id=self.cleaned_data["gateway_id"])

        return CreateScreeningOrderGatewayMessage.call(
            participant,
            gateway
        )
