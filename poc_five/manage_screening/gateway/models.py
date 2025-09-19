from django.db import models
from participant.models import Participant
import uuid

class Message(models.Model):
    TYPE_FHIR = 'FHIR'
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway = models.ForeignKey('Gateway', to_field="id", on_delete=models.PROTECT)
    participant = models.ForeignKey('participant.Participant', on_delete=models.PROTECT)
    type = models.CharField(max_length=30)
    payload = models.TextField()
    destination = models.CharField(max_length=300)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.id}'

class Gateway(models.Model):
    id = models.UUIDField(primary_key=True)
    order_url = models.CharField()
    setting = models.ForeignKey('Setting', on_delete=models.PROTECT)

    # Azure Relay configuration fields
    relay_namespace = models.CharField(
        max_length=255,
        help_text="Azure Relay namespace (e.g., myrelay.servicebus.windows.net)"
    )
    relay_hybrid_connection = models.CharField(
        max_length=255,
        help_text="Azure Relay hybrid connection name"
    )
    relay_key_name = models.CharField(
        max_length=255,
        help_text="Azure Relay shared access policy name"
    )
    relay_shared_access_key_variable_name = models.CharField(
        max_length=255,
        help_text="Environment variable name containing the shared access key"
    )

    def __str__(self):
        return f'{self.id}'

class Setting(models.Model):
    name = models.CharField(max_length=30)

    def __str__(self):
        return f'{self.name}'
