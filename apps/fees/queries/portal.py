"""Queries — student/parent portal reads."""

from apps.accounts.models.guardian import StudentGuardianLink
from apps.fees.models import Receipt


def guardian_portal_link(guardian_user_id, student_user_id):
    """The active guardian link granting portal access to a child, or None."""
    return StudentGuardianLink.objects.filter(
        guardian_id=guardian_user_id, student_id=student_user_id,
        has_portal_access=True, is_active=True,
    ).first()


def list_receipts_for_student(student_user_id):
    """Receipts for a student, keyed by the student's User id (enrollment-seam safe)."""
    return Receipt.objects.filter(
        payment__invoice__student__student_profile__user_id=student_user_id, is_active=True
    ).select_related("payment", "payment__invoice").order_by("-issued_at")
