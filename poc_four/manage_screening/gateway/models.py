from django.db import models
from participant.models import Participant

class Message(models.Model):
    TYPE_FHIR = 'fhir'

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
    order_url = models.URLField()
    setting = models.ForeignKey('Setting', on_delete=models.PROTECT)

    def __str__(self):
        return f'{self.id}'

class Setting(models.Model):
    name = models.CharField(max_length=30)

    def __str__(self):
        return f'{self.name}'
