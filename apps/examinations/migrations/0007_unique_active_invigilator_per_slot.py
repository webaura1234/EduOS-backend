# Generated manually for invigilator soft-delete + unique constraint fix

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("examinations", "0006_examseatingsession"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="invigilatorduty",
            name="unique_invigilator_per_slot",
        ),
        migrations.AddConstraint(
            model_name="invigilatorduty",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True),
                fields=("schedule_slot", "faculty"),
                name="unique_active_invigilator_per_slot",
            ),
        ),
    ]
