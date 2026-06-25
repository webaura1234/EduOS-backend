from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ("examinations", "0005_examscheduleslot_required_invigilators"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExamSeatingSession",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
                ("version", models.IntegerField(default=1)),
                ("name", models.CharField(max_length=150)),
                ("start_at", models.DateTimeField()),
                ("end_at", models.DateTimeField()),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_created",
                        to="accounts.user",
                    ),
                ),
                (
                    "exam",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="seating_sessions",
                        to="examinations.exam",
                    ),
                ),
                (
                    "hall_room",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="exam_seating_sessions",
                        to="academics.room",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_updated",
                        to="accounts.user",
                    ),
                ),
            ],
            options={
                "verbose_name": "Exam Seating Session",
                "verbose_name_plural": "Exam Seating Sessions",
                "db_table": "examinations_exam_seating_session",
            },
        ),
        migrations.AddField(
            model_name="examscheduleslot",
            name="seating_session",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="schedule_slots",
                to="examinations.examseatingsession",
            ),
        ),
    ]
