import os
from django.core.management.base import BaseCommand
from participant.models import Participant
from gateway.models import Gateway, Setting
from provider.models import Provider, Clinic, ClinicSlot, Appointment
from django.contrib.auth.models import User
from django.db.utils import IntegrityError
from datetime import datetime, time, timedelta, date


class Command(BaseCommand):
    def handle(self, *args, **kwargs):
        records = [
                {"first_name": "Margaret", "last_name": "Smith", "nhs_number": "90000000001", "date_of_birth": "1955-04-10"},
                {"first_name": "Patricia", "last_name": "Johnson", "nhs_number": "90000000002", "date_of_birth": "1958-06-15"},
                {"first_name": "Linda", "last_name": "Brown", "nhs_number": "90000000003", "date_of_birth": "1962-09-23"},
                {"first_name": "Barbara", "last_name": "Williams", "nhs_number": "90000000004", "date_of_birth": "1965-02-05"},
                {"first_name": "Elizabeth", "last_name": "Jones", "nhs_number": "90000000005", "date_of_birth": "1953-11-30"},
                {"first_name": "Jennifer", "last_name": "Miller", "nhs_number": "90000000006", "date_of_birth": "1961-08-19"},
                {"first_name": "Maria", "last_name": "Davis", "nhs_number": "90000000007", "date_of_birth": "1957-05-28"},
                {"first_name": "Susan", "last_name": "Garcia", "nhs_number": "90000000008", "date_of_birth": "1956-12-03"},
                {"first_name": "Deborah", "last_name": "Rodriguez", "nhs_number": "90000000009", "date_of_birth": "1960-07-14"},
                {"first_name": "Dorothy", "last_name": "Wilson", "nhs_number": "90000000010", "date_of_birth": "1954-01-22"},
                ]

        for record in records:
            Participant.objects.create(**record)


        #TODO this should be Provider or maybe related to provider? Provider might have many settings?
        setting = Setting.objects.create(
                name="Alpha Hospital Trust"
                )

        Gateway.objects.create(
                setting = setting,
                id = os.environ.get("GATEWAY_ID"),
                order_url = "https://local-order-service/order",
                relay_namespace = os.environ.get("AZURE_RELAY_NAMESPACE", "graham-relay-test.servicebus.windows.net"),
                relay_hybrid_connection = os.environ.get("AZURE_RELAY_HYBRID_CONNECTION", "graham-relay-test-hc"),
                relay_key_name = os.environ.get("AZURE_RELAY_KEY_NAME", "RootManageSharedAccessKey"),
                relay_shared_access_key_variable_name = "AZURE_RELAY_SHARED_ACCESS_KEY"
                )

        provider = Provider.objects.create(
                name="Alpha Hospital Trust"
                )

        clinic = provider.clinics.create(
                date=date(2025, 8, 11)
                )

        participants = Participant.objects.all()

        start_time = datetime.combine(clinic.date, time(9, 0, 0))
        slot_duration = timedelta(minutes=15)

        for participant in participants:
            # Create the slot with a timedelta duration
            clinic_slot = clinic.slots.create(
                    start_time=start_time,
                    duration=slot_duration
                    )
            clinic_slot.appointments.create(
                    participant=participant
                    )
            # Increment start_time by the slot duration for the next iteration
            start_time += slot_duration

            
        # Create a superuser if one doesn't exist
        try:
            if not User.objects.filter(username="admin").exists():
                User.objects.create_superuser(
                    username="admin",
                    email="admin@example.com",
                    password=os.environ.get("DJANGO_SUPERUSER_PASSWORD"),
                )
                self.stdout.write(self.style.SUCCESS("Superuser 'admin' created successfully!"))
            else:
                self.stdout.write(self.style.WARNING("Superuser 'admin' already exists."))
        except IntegrityError:
            self.stdout.write(self.style.ERROR("Error creating superuser!"))

        self.stdout.write(self.style.SUCCESS("Database seeding completed!"))
