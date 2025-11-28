from django.db import models
import uuid

class GatewayAction(models.Model):
    # Action type constants matching schema
    TYPE_WORKLIST_CREATE = 'worklist.create_item'
    TYPE_WORKLIST_REMOVE = 'worklist.remove_item'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    gateway = models.ForeignKey('Gateway', to_field="id", on_delete=models.PROTECT)
    type = models.CharField(max_length=50)
    payload = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f'{self.id}'

class Gateway(models.Model):
    id = models.UUIDField(primary_key=True)
    order_url = models.CharField()
    setting = models.ForeignKey('Setting', on_delete=models.PROTECT)

    # POC6: HTTP API configuration for gateway MWL server
    api_url = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        help_text="Gateway API URL for MWL (e.g., http://orthanc-mwl-gateway:5000/api/worklist)"
    )

    # Azure Relay configuration fields (POC5 - kept for compatibility)
    relay_namespace = models.CharField(
        max_length=255,
        blank=True,
        help_text="Azure Relay namespace (e.g., myrelay.servicebus.windows.net)"
    )
    relay_hybrid_connection = models.CharField(
        max_length=255,
        blank=True,
        help_text="Azure Relay hybrid connection name"
    )
    relay_key_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Azure Relay shared access policy name"
    )
    relay_shared_access_key_variable_name = models.CharField(
        max_length=255,
        blank=True,
        help_text="Environment variable name containing the shared access key"
    )

    def __str__(self):
        return f'{self.id}'

class Setting(models.Model):
    name = models.CharField(max_length=30)

    def __str__(self):
        return f'{self.name}'
