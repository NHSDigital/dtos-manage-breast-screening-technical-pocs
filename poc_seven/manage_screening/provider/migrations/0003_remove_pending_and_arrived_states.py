# Generated manually for POC

from django.db import migrations, models


def update_pending_and_arrived_to_checked_in(apps, schema_editor):
    """Update all 'pending' and 'arrived' appointments to 'checked_in'"""
    Appointment = apps.get_model('provider', 'Appointment')
    Appointment.objects.filter(state__in=['pending', 'arrived']).update(state='checked_in')


class Migration(migrations.Migration):

    dependencies = [
        ('provider', '0002_alter_appointment_state'),
    ]

    operations = [
        # First update existing data
        migrations.RunPython(update_pending_and_arrived_to_checked_in, migrations.RunPython.noop),

        # Then update the field definition
        migrations.AlterField(
            model_name='appointment',
            name='state',
            field=models.CharField(
                choices=[
                    ('checked_in', 'Checked_in'),
                    ('sent_to_modality', 'Sent_to_modality'),
                    ('in_progress', 'In_progress'),
                    ('complete', 'Complete'),
                    ('cancelled', 'Cancelled')
                ],
                default='checked_in',
                max_length=20
            ),
        ),
    ]
