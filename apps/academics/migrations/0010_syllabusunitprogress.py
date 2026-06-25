# Section-scoped syllabus progress; units become definition-only.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0009_studymaterialfolder"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="SyllabusUnitProgress",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("version", models.IntegerField(default=1)),
                ("completed_at", models.DateTimeField()),
                ("batch", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="syllabus_unit_progress",
                    to="academics.batch",
                )),
                ("branch", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="syllabus_unit_progress",
                    to="organizations.branch",
                )),
                ("completed_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="syllabus_unit_progress_marked",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("created_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="%(app_label)s_%(class)s_created",
                    to=settings.AUTH_USER_MODEL,
                )),
                ("unit", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="section_progress",
                    to="academics.syllabusunit",
                )),
                ("updated_by", models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name="%(app_label)s_%(class)s_updated",
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                "db_table": "academics_syllabus_unit_progress",
            },
        ),
        migrations.AddIndex(
            model_name="syllabusunitprogress",
            index=models.Index(fields=["branch", "batch"], name="academics_sy_branch__a8f3c1_idx"),
        ),
        migrations.AddConstraint(
            model_name="syllabusunitprogress",
            constraint=models.UniqueConstraint(
                fields=("batch", "unit"),
                name="academics_syllabus_progress_batch_unit_uniq",
            ),
        ),
        migrations.RemoveField(model_name="syllabusunit", name="completed_at"),
        migrations.RemoveField(model_name="syllabusunit", name="completed_by"),
        migrations.RemoveField(model_name="syllabusunit", name="is_completed"),
    ]
