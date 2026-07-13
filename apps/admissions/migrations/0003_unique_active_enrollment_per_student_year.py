# Partial unique — only one active enrollment per student per academic year

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("admissions", "0002_enquiry_custom_fields_enquiry_is_public_submission_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="studentenrollment",
            name="unique_enrollment_per_student_year",
        ),
        migrations.AddConstraint(
            model_name="studentenrollment",
            constraint=models.UniqueConstraint(
                condition=models.Q(is_active=True),
                fields=("student_profile", "academic_year"),
                name="unique_active_enrollment_per_student_year",
            ),
        ),
    ]
