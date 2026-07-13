# Enrollment seam — InternalMark.student_profile → StudentEnrollment

import django.db.models.deletion
from django.db import migrations, models


def _backfill_internal_mark_student(apps, schema_editor):
    InternalMark = apps.get_model("examinations", "InternalMark")
    StudentEnrollment = apps.get_model("admissions", "StudentEnrollment")

    for mark in InternalMark.objects.all().iterator():
        enrollment = (
            StudentEnrollment.objects.filter(
                student_profile_id=mark.student_profile_id,
                branch_id=mark.branch_id,
                is_active=True,
            )
            .order_by("-created_at")
            .first()
        )
        if enrollment is None:
            enrollment = (
                StudentEnrollment.objects.filter(
                    student_profile_id=mark.student_profile_id,
                    branch_id=mark.branch_id,
                )
                .order_by("-created_at")
                .first()
            )
        if enrollment is None:
            raise RuntimeError(
                f"Cannot backfill InternalMark {mark.pk}: no enrollment for profile "
                f"{mark.student_profile_id} in branch {mark.branch_id}"
            )
        mark.student_id = enrollment.pk
        mark.save(update_fields=["student_id"])


class Migration(migrations.Migration):

    dependencies = [
        ("admissions", "0002_enquiry_custom_fields_enquiry_is_public_submission_and_more"),
        ("examinations", "0007_unique_active_invigilator_per_slot"),
    ]

    operations = [
        migrations.AddField(
            model_name="internalmark",
            name="student",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="internal_marks",
                to="admissions.studentenrollment",
            ),
        ),
        migrations.RunPython(_backfill_internal_mark_student, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name="internalmark",
            name="unique_internal_mark_per_student_subject",
        ),
        migrations.RemoveField(
            model_name="internalmark",
            name="student_profile",
        ),
        migrations.AlterField(
            model_name="internalmark",
            name="student",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="internal_marks",
                to="admissions.studentenrollment",
            ),
        ),
        migrations.AddConstraint(
            model_name="internalmark",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True),
                fields=("student", "subject"),
                name="unique_internal_mark_per_student_subject",
            ),
        ),
    ]
