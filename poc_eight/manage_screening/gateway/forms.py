from django import forms
from gateway.models import Gateway
from provider.models import Appointment
from gateway.services.create_worklist_item_create_action import CreateWorklistItemCreateAction

class ScreeningOrderGatewayActionForm(forms.Form):
    appointment_id = forms.UUIDField(widget=forms.HiddenInput())
    gateway_id = forms.UUIDField(widget=forms.HiddenInput())

    def save(self):
        appointment = Appointment.objects.get(id=self.cleaned_data["appointment_id"])
        gateway = Gateway.objects.get(id=self.cleaned_data["gateway_id"])

        return CreateWorklistItemCreateAction.call(
            appointment,
            gateway
        )
