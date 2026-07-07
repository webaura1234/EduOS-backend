# Generated manually for gallery photos

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("communications", "0003_announcementread"),
        ("organizations", "0006_branch_working_days"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="GalleryPhoto",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("version", models.IntegerField(default=1)),
                ("title", models.CharField(max_length=255)),
                ("caption", models.TextField(blank=True, default="")),
                ("image_url", models.URLField(max_length=500)),
                ("branch", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="gallery_photos",
                    to="organizations.branch",
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="%(app_label)s_%(class)s_created",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="%(app_label)s_%(class)s_updated",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "db_table": "communications_gallery_photo",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(fields=["branch", "-created_at"], name="communicati_branch__gallery_idx"),
                ],
            },
        ),
    ]
