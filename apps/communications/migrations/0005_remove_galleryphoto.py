# Generated migration — remove legacy GalleryPhoto after data migrated to apps.gallery

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("communications", "0004_galleryphoto"),
        ("gallery", "0002_migrate_legacy_gallery"),
    ]

    operations = [
        migrations.DeleteModel(
            name="GalleryPhoto",
        ),
    ]
