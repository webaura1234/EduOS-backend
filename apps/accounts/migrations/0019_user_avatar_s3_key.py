# Generated migration — swap unused ImageField avatar for S3/R2 avatar_s3_key.
#
# The legacy `avatar` ImageField assumed Django media storage but was never exposed
# via any API or UI. The platform standard is S3/R2 keys + signed URLs (see tenant
# logo_s3_key). No data migration is required.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0018_refreshtoken_current_access_jti"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="avatar_s3_key",
            field=models.CharField(blank=True, default="", max_length=500),
        ),
        migrations.RemoveField(
            model_name="user",
            name="avatar",
        ),
    ]
