# Generated manually for LicensePayment.idempotency_key length

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0020_delete_studentplatformsubscription"),
    ]

    operations = [
        migrations.AlterField(
            model_name="licensepayment",
            name="idempotency_key",
            field=models.CharField(blank=True, max_length=255, null=True, unique=True),
        ),
    ]
