from django.urls import path
from .views import (
    get_clinic,
    clinic_index,
    appointment_statuses,
    get_appointment,
    appointment_images,
    appointment_images_stream,
    appointment_status_stream
)

urlpatterns = [
    path("clinics", clinic_index, name="clinic_index"),
    path("clinic/<uuid:clinic_id>", get_clinic, name="get_clinic"),
    path("clinic/<uuid:clinic_id>/appointment/<uuid:appointment_id>", get_appointment, name="get_appointment"),
    path("api/clinic/<uuid:clinic_id>/statuses", appointment_statuses, name="appointment_statuses"),
    path("api/clinic/<uuid:clinic_id>/appointment/<uuid:appointment_id>/images", appointment_images, name="appointment_images"),
    path("api/clinic/<uuid:clinic_id>/appointment/<uuid:appointment_id>/images/stream", appointment_images_stream, name="appointment_images_stream"),
    path("api/clinic/<uuid:clinic_id>/appointment/<uuid:appointment_id>/status/stream", appointment_status_stream, name="appointment_status_stream"),
]
        

