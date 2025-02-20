import os
import uuid
from django.core.management.base import BaseCommand
from participant.models import Participant
from gateway.models import Gateway, Setting
from django.contrib.auth.models import User
from django.db.utils import IntegrityError


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

        setting = Setting.objects.create(
            name="Alpha Hospital Trust"
            )

        Gateway.objects.create(
            setting = setting,
            id = uuid.uuid4(),
            order_url = "https://local-order-service/order"
            )
            
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


