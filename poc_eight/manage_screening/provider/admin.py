from django.contrib import admin
from provider.models import Provider, Clinic, ClinicSlot, Appointment

# Register your models here.
admin.site.register(Provider)
admin.site.register(Clinic)
admin.site.register(ClinicSlot)
admin.site.register(Appointment)

