# Generated manually for ReportStatus.EXPIRED

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("analytics", "0006_reporting_framework_v1"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reportexport",
            name="status",
            field=models.CharField(
                choices=[
                    ("queued", "Queued"),
                    ("running", "Running"),
                    ("ready", "Ready"),
                    ("failed", "Failed"),
                    ("timed_out", "Timed Out"),
                    ("expired", "Expired"),
                ],
                db_index=True,
                default="queued",
                max_length=15,
            ),
        ),
    ]
