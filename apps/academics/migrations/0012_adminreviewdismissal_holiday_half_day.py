# Generated manually for academics admin review dismissals and holiday half-day type.

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0011_rename_academics_s_branch__folder_idx_academics_s_branch__0811f2_idx_and_more"),
        ("organizations", "0006_branch_working_days"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="holiday",
            name="holiday_type",
            field=models.CharField(
                choices=[
                    ("public", "Public Holiday"),
                    ("school", "School Holiday"),
                    ("exam", "Exam Day"),
                    ("half_day", "Half Day"),
                    ("optional", "Optional Holiday"),
                ],
                default="public",
                max_length=20,
            ),
        ),
        migrations.AlterField(
            model_name="calendarchange",
            name="change_type",
            field=models.CharField(
                choices=[
                    ("working_days", "Working days"),
                    ("period", "Period"),
                    ("holiday", "Holiday"),
                    ("review_dismissed", "Review dismissed"),
                ],
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="AdminReviewDismissal",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("version", models.IntegerField(default=1)),
                ("review_id", models.CharField(max_length=64)),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="review_dismissals",
                        to="organizations.branch",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_updated",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "academics_admin_review_dismissal",
                "indexes": [
                    models.Index(fields=["branch", "review_id"], name="academics_r_branch__rev_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("branch", "review_id"),
                        name="academics_review_dismissal_branch_review_uniq",
                    ),
                ],
            },
        ),
    ]
