"""Migrate legacy communications GalleryPhoto rows into gallery app."""

from django.db import migrations
from django.utils.text import slugify


def forwards(apps, schema_editor):
    LegacyPhoto = apps.get_model("communications", "GalleryPhoto")
    GalleryAlbum = apps.get_model("gallery", "GalleryAlbum")
    GalleryImage = apps.get_model("gallery", "GalleryImage")
    AcademicYear = apps.get_model("academics", "AcademicYear")

    legacy = LegacyPhoto.objects.filter(is_active=True).order_by("branch_id", "created_at")
    albums_by_branch = {}

    for photo in legacy:
        branch_id = photo.branch_id
        if branch_id not in albums_by_branch:
            year = (
                AcademicYear.objects.filter(branch_id=branch_id, is_current=True).first()
                or AcademicYear.objects.filter(branch_id=branch_id).order_by("-start_date").first()
            )
            if year is None:
                continue
            album = GalleryAlbum.objects.create(
                branch_id=branch_id,
                academic_year=year,
                title="Campus Photos",
                slug=slugify("campus-photos")[:120],
                description="Migrated from legacy gallery.",
                visibility="students",
                total_images=0,
                created_by_id=photo.created_by_id,
                updated_by_id=photo.updated_by_id,
            )
            albums_by_branch[branch_id] = album
        album = albums_by_branch[branch_id]
        GalleryImage.objects.create(
            album=album,
            external_url=photo.image_url,
            original_file_name=photo.title or "legacy.jpg",
            sort_order=album.total_images,
            processing_status="ready",
            uploaded_by_id=photo.created_by_id,
            created_by_id=photo.created_by_id,
            updated_by_id=photo.updated_by_id,
        )
        album.total_images += 1
        album.save(update_fields=["total_images"])


def backwards(apps, schema_editor):
    GalleryAlbum = apps.get_model("gallery", "GalleryAlbum")
    GalleryAlbum.objects.filter(slug="campus-photos", title="Campus Photos").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("gallery", "0001_initial"),
        ("communications", "0004_galleryphoto"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
