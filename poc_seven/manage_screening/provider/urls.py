from django.urls import path
from .views import get_clinic, clinic_index, appointment_statuses, get_appointment

urlpatterns = [
    path("clinics", clinic_index, name="clinic_index"),
    path("clinic/<uuid:clinic_id>", get_clinic, name="get_clinic"),
    path("clinic/<uuid:clinic_id>/appointment/<uuid:appointment_id>", get_appointment, name="get_appointment"),
    path("api/clinic/<uuid:clinic_id>/statuses", appointment_statuses, name="appointment_statuses"),
]
        

