from django.db import models
import uuid
from provider.models import Appointment

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


class Study(models.Model):
    """DICOM Study received from gateway PACS"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    appointment = models.ForeignKey(Appointment, related_name='studies', on_delete=models.PROTECT)

    # DICOM identifiers
    accession_number = models.CharField(max_length=100, unique=True, db_index=True)
    study_instance_uid = models.CharField(max_length=255, unique=True, db_index=True)

    # Study metadata
    modality = models.CharField(max_length=10)
    study_date = models.CharField(max_length=8, help_text="DICOM date format: YYYYMMDD")
    study_time = models.CharField(max_length=6, help_text="DICOM time format: HHMMSS")
    study_description = models.CharField(max_length=255, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Studies"

    def __str__(self):
        return f"{self.accession_number} - {self.study_description}"


class Series(models.Model):
    """DICOM Series within a Study"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    study = models.ForeignKey(Study, related_name='series', on_delete=models.CASCADE)

    # DICOM identifiers
    series_instance_uid = models.CharField(max_length=255, unique=True, db_index=True)
    series_number = models.CharField(max_length=20)

    # Series metadata
    series_description = models.CharField(max_length=255, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Series"

    def __str__(self):
        return f"{self.study.accession_number} - Series {self.series_number}"


class Image(models.Model):
    """DICOM Image/Instance within a Series"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    series = models.ForeignKey(Series, related_name='images', on_delete=models.CASCADE)

    # DICOM identifiers
    sop_instance_uid = models.CharField(max_length=255, db_index=True)
    instance_number = models.CharField(max_length=20)

    # Image dimensions
    rows = models.IntegerField()
    columns = models.IntegerField()

    # Acquisition metadata (mammography-specific)
    view_position = models.CharField(max_length=10, blank=True, help_text="e.g., CC, MLO")
    laterality = models.CharField(max_length=1, blank=True, help_text="L or R")

    # Dose and exposure parameters
    organ_dose = models.CharField(max_length=20, blank=True, help_text="Mean Glandular Dose (MGD) in mGy")
    entrance_dose_in_mgy = models.CharField(max_length=20, blank=True, help_text="Entrance surface dose in mGy")
    kvp = models.CharField(max_length=10, blank=True, help_text="Tube voltage in kV")
    exposure_in_uas = models.CharField(max_length=20, blank=True, help_text="Tube current-time product in µAs")
    anode_target_material = models.CharField(max_length=20, blank=True, help_text="e.g., TUNGSTEN")
    filter_material = models.CharField(max_length=20, blank=True, help_text="e.g., RHODIUM")
    filter_thickness = models.CharField(max_length=10, blank=True, help_text="Filter thickness in mm")

    # Thumbnail file
    thumbnail = models.ImageField(upload_to='thumbnails/', help_text="JPEG thumbnail image file")

    # Timestamps
    received_at = models.DateTimeField(help_text="When image was received at gateway")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['series', 'sop_instance_uid'],
                name='unique_image_per_series'
            )
        ]

    def __str__(self):
        return f"{self.series.study.accession_number} - Instance {self.instance_number}"
