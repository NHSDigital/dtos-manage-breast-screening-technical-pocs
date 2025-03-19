from django import forms
from gateway.models import Message, Gateway
from provider.models import Appointment
from participant.models import Participant
from gateway.services.create_screening_order_gateway_message import CreateScreeningOrderGatewayMessage

class ScreeningOrderGatewayMessageForm(forms.Form):
    appointment_id = forms.UUIDField(widget=forms.HiddenInput())
    gateway_id = forms.UUIDField(widget=forms.HiddenInput())

    def save(self):
        appointment = Appointment.objects.get(id=self.cleaned_data["appointment_id"])
        gateway = Gateway.objects.get(id=self.cleaned_data["gateway_id"])

        return CreateScreeningOrderGatewayMessage.call(
            appointment,
            gateway
        )
