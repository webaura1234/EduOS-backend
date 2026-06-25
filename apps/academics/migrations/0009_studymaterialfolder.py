# Study material folders — per-class organization.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0008_studymaterial_class_only"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="StudyMaterialFolder",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("version", models.IntegerField(default=1)),
                ("name", models.CharField(max_length=100)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("batch", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="study_material_folders",
                    to="academics.batch",
                )),
                ("branch", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="study_material_folders",
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
                "db_table": "academics_study_material_folder",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.AddIndex(
            model_name="studymaterialfolder",
            index=models.Index(fields=["branch", "batch"], name="academics_s_branch__folder_idx"),
        ),
        migrations.AddConstraint(
            model_name="studymaterialfolder",
            constraint=models.UniqueConstraint(
                fields=("batch", "name"),
                name="academics_study_material_folder_batch_name_uniq",
            ),
        ),
        migrations.AddField(
            model_name="studymaterial",
            name="folder",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="materials",
                to="academics.studymaterialfolder",
            ),
        ),
    ]
