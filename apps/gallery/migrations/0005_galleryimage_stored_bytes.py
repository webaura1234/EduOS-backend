# Generated manually for stored_bytes metering field.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("gallery", "0004_album_visibility_audiences"),
    ]

    operations = [
        migrations.AddField(
            model_name="galleryimage",
            name="stored_bytes",
            field=models.PositiveIntegerField(default=0),
        ),
    ]
