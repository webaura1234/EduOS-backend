# Gallery app initial migration

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("academics", "0001_initial"),
        ("organizations", "0006_branch_working_days"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GalleryAlbum",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("version", models.IntegerField(default=1)),
                ("title", models.CharField(max_length=255)),
                ("slug", models.SlugField(max_length=120)),
                ("description", models.TextField(blank=True, default="")),
                ("cover_image_key", models.CharField(blank=True, default="", max_length=512)),
                ("total_images", models.PositiveIntegerField(default=0)),
                ("visibility", models.CharField(
                    choices=[
                        ("students", "Students"),
                        ("parents", "Parents"),
                        ("faculty", "Faculty"),
                        ("staff_only", "Staff only"),
                        ("private", "Private"),
                    ],
                    default="students",
                    max_length=20,
                )),
                ("event_tag", models.CharField(blank=True, default="", max_length=100)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("academic_year", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="gallery_albums",
                    to="academics.academicyear",
                )),
                ("batch", models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="gallery_albums",
                    to="academics.batch",
                )),
                ("branch", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="gallery_album_list",
                    to="organizations.branch",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="gallery_galleryalbum_created",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="gallery_galleryalbum_updated",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "db_table": "gallery_album",
                "ordering": ["sort_order", "-created_at"],
            },
        ),
        migrations.CreateModel(
            name="GalleryImage",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("version", models.IntegerField(default=1)),
                ("image_key", models.CharField(blank=True, default="", max_length=512)),
                ("thumbnail_key", models.CharField(blank=True, default="", max_length=512)),
                ("staging_key", models.CharField(blank=True, default="", max_length=512)),
                ("external_url", models.URLField(blank=True, default="", max_length=500)),
                ("original_file_name", models.CharField(blank=True, default="", max_length=255)),
                ("file_size", models.PositiveIntegerField(default=0)),
                ("width", models.PositiveIntegerField(default=0)),
                ("height", models.PositiveIntegerField(default=0)),
                ("sort_order", models.PositiveIntegerField(default=0)),
                ("content_hash", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("processing_status", models.CharField(
                    choices=[("pending", "Pending"), ("ready", "Ready"), ("failed", "Failed")],
                    default="pending",
                    max_length=20,
                )),
                ("processing_error", models.TextField(blank=True, default="")),
                ("album", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="images",
                    to="gallery.galleryalbum",
                )),
                ("uploaded_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="gallery_uploads",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="gallery_galleryimage_created",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="gallery_galleryimage_updated",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "db_table": "gallery_image",
                "ordering": ["sort_order", "-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="galleryalbum",
            index=models.Index(fields=["branch", "batch", "slug"], name="gallery_alb_branch_batch_slug"),
        ),
        migrations.AddIndex(
            model_name="galleryalbum",
            index=models.Index(fields=["branch", "-created_at"], name="gallery_alb_branch_created"),
        ),
        migrations.AddConstraint(
            model_name="galleryalbum",
            constraint=models.UniqueConstraint(
                fields=("branch", "batch", "slug"),
                name="unique_gallery_album_slug_per_scope",
            ),
        ),
        migrations.AddIndex(
            model_name="galleryimage",
            index=models.Index(fields=["album", "sort_order"], name="gallery_img_album_sort"),
        ),
        migrations.AddIndex(
            model_name="galleryimage",
            index=models.Index(fields=["album", "content_hash"], name="gallery_img_album_hash"),
        ),
    ]
