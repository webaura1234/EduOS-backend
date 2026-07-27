# Convert gallery album visibility from single enum string to audience list (JSON).

from django.db import migrations, models


def default_visibility():
    return ["students"]


def _legacy_to_list(value: str) -> list:
    if value in ("private", "", None):
        return []
    if value == "staff_only":
        return ["faculty"]
    if value in ("students", "parents", "faculty"):
        return [value]
    return ["students"]


def forwards(apps, schema_editor):
    GalleryAlbum = apps.get_model("gallery", "GalleryAlbum")
    for album in GalleryAlbum.objects.all().iterator():
        album.visibility_audiences = _legacy_to_list(album.visibility)
        album.save(update_fields=["visibility_audiences"])


class Migration(migrations.Migration):

    dependencies = [
        ("gallery", "0003_rename_gallery_alb_branch_batch_slug_gallery_alb_branch__17b786_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="galleryalbum",
            name="visibility_audiences",
            field=models.JSONField(blank=True, default=default_visibility),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="galleryalbum",
            name="visibility",
        ),
        migrations.RenameField(
            model_name="galleryalbum",
            old_name="visibility_audiences",
            new_name="visibility",
        ),
    ]
