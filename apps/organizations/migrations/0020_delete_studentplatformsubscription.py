# Generated manually — retire legacy StudentPlatformSubscription ledger.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("organizations", "0019_tenantsettings_faculty_id_format_and_more"),
    ]

    operations = [
        migrations.DeleteModel(
            name="StudentPlatformSubscription",
        ),
    ]
