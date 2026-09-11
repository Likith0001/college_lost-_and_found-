# Generated manually to preserve the timestamps of all existing reports.

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('lost_and_found', '0001_initial'),
    ]

    operations = [
        migrations.RenameField(
            model_name='item',
            old_name='date_reported',
            new_name='submitted_at',
        ),
        migrations.AlterField(
            model_name='item',
            name='submitted_at',
            field=models.DateTimeField(default=django.utils.timezone.now, editable=False),
        ),
        migrations.AlterModelOptions(
            name='item',
            options={'ordering': ['-submitted_at']},
        ),
    ]
