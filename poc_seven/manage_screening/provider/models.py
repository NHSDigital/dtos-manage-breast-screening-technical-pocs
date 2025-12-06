from django.db import models
from enum import Enum
import uuid
from participant.models import Participant

class Provider(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name

class Clinic(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    date = models.DateField()
    provider = models.ForeignKey(Provider, related_name='clinics', on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.provider.name}: {self.date}'

class ClinicSlot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    start_time = models.TimeField()
    duration = models.DurationField()
    clinic = models.ForeignKey(Clinic, related_name='slots', on_delete=models.CASCADE)

    def __str__(self):
        return f'{self.clinic}: {self.start_time}'

class AppointmentState(Enum):
    CHECKED_IN = 'checked_in'
    SENT_TO_MODALITY = 'sent_to_modality'
    IN_PROGRESS = 'in_progress'
    COMPLETE = 'complete'
    CANCELLED = 'cancelled'

class Appointment(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    clinic_slot = models.ForeignKey(ClinicSlot, related_name='appointments', on_delete=models.CASCADE)
    participant = models.ForeignKey(Participant, related_name='appointments', on_delete=models.CASCADE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    state = models.CharField(
        max_length=20,
        choices=[(state.value, state.name.capitalize()) for state in AppointmentState],
        default=AppointmentState.CHECKED_IN.value
    )

    def __str__(self):
        return f'{self.participant}: {self.clinic_slot} - {self.state}'

    def send_to_modality(self):
        self.state = AppointmentState.SENT_TO_MODALITY.value
        self.save()

