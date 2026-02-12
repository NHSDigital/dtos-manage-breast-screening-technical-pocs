# Generated manually on 2025-12-04

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gateway', '0002_series_image_study_series_study'),
    ]

    operations = [
        migrations.AlterField(
            model_name='image',
            name='sop_instance_uid',
            field=models.CharField(db_index=True, max_length=255),
        ),
        migrations.AddConstraint(
            model_name='image',
            constraint=models.UniqueConstraint(
                fields=['series', 'sop_instance_uid'],
                name='unique_image_per_series'
            ),
        ),
    ]
