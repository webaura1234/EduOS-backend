"""Per-link notification channel routing for guardian links."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_studentprofile_current_enrollment"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentguardianlink",
            name="notification_channels",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name="studentguardianlink",
            name="relationship",
            field=models.CharField(
                choices=[
                    ("father", "Father"),
                    ("mother", "Mother"),
                    ("step_father", "Step father"),
                    ("step_mother", "Step mother"),
                    ("guardian", "Guardian"),
                    ("custodian", "Custodian"),
                    ("sibling", "Sibling"),
                    ("grandparent", "Grandparent"),
                    ("other", "Other"),
                ],
                default="guardian",
                max_length=20,
            ),
        ),
    ]
