from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0017_walkthroughcompletion"),
    ]

    operations = [
        migrations.AddField(
            model_name="refreshtoken",
            name="current_access_jti",
            field=models.CharField(
                blank=True,
                default="",
                help_text="JTI of the latest access token issued for this session (enables remote revoke).",
                max_length=36,
            ),
        ),
    ]
