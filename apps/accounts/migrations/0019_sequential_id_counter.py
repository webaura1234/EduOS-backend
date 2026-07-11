"""Generalise StudentIDCounter → SequentialIdCounter (student + faculty)."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0018_refreshtoken_current_access_jti"),
    ]

    operations = [
        # db_table stays "accounts_student_id_counter", so this is a Django-state
        # rename only — no ALTER TABLE, existing counter rows are preserved.
        migrations.RenameModel(
            old_name="StudentIDCounter",
            new_name="SequentialIdCounter",
        ),
        migrations.AlterModelOptions(
            name="sequentialidcounter",
            options={
                "verbose_name": "Sequential ID Counter",
                "verbose_name_plural": "Sequential ID Counters",
            },
        ),
        migrations.AlterModelTable(
            name="sequentialidcounter",
            table="accounts_student_id_counter",
        ),
        migrations.AddField(
            model_name="sequentialidcounter",
            name="purpose",
            field=models.CharField(
                choices=[("student", "Student"), ("faculty", "Faculty")],
                default="student",
                help_text="Which population this counter numbers (student / faculty).",
                max_length=16,
            ),
        ),
        migrations.AlterField(
            model_name="sequentialidcounter",
            name="academic_year",
            field=models.CharField(
                blank=True,
                default="",
                help_text="'2025-2026' for year-scoped counters; '' for continuous.",
                max_length=9,
            ),
        ),
        migrations.AlterField(
            model_name="sequentialidcounter",
            name="branch",
            field=models.ForeignKey(
                db_index=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="id_counters",
                to="organizations.branch",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="sequentialidcounter",
            unique_together={("branch", "purpose", "academic_year")},
        ),
    ]
