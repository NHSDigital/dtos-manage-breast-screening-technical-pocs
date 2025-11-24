from django.urls import path
from .views import get_clinic, clinic_index, appointment_statuses

urlpatterns = [
    path("clinics", clinic_index, name="clinic_index"),
    path("clinic/<uuid:clinic_id>", get_clinic, name="get_clinic"),
    path("api/clinic/<uuid:clinic_id>/statuses", appointment_statuses, name="appointment_statuses"),
]
        

