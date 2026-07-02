"""
Student ID generation — gap-free sequential IDs per branch per academic year.

generate_student_id() is called during student user creation when
custom_login_id is not explicitly provided. It uses a row-level lock
(SELECT FOR UPDATE) to prevent duplicate IDs under concurrent admits.

Format: "{BRANCH_CODE}/{YEAR_SHORT}/{SEQUENCE:05d}"
Example: "ABCS/2025/00142"
"""

from django.db import transaction


def generate_student_id(branch, academic_year: str) -> str:
    """
    Return the next sequential student ID for (branch, academic_year).

    Args:
        branch: organizations.Branch instance (must have .code attribute)
        academic_year: string in "2025-2026" format

    Returns:
        str like "ABCS/2025/00142"
    """
    from apps.accounts.models.security import StudentIDCounter

    with transaction.atomic():
        counter, _ = StudentIDCounter.objects.select_for_update().get_or_create(
            branch=branch,
            academic_year=academic_year,
            defaults={"last_sequence": 0},
        )
        counter.last_sequence += 1
        counter.save(update_fields=["last_sequence"])

    year_short = academic_year[:4]
    branch_code = (branch.code or "SCH").upper()
    return f"{branch_code}/{year_short}/{counter.last_sequence:05d}"
