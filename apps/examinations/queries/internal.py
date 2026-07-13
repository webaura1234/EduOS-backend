"""Queries — InternalMark (internal/continuous assessment)."""

from apps.examinations.models import InternalMark
from apps.fees.queries.structure import get_student_in_branch


def list_recorded_by(branch_id, faculty_user_id):
    return (
        InternalMark.objects.filter(
            branch_id=branch_id, recorded_by_id=faculty_user_id, is_active=True,
        )
        .select_related("student__student_profile__user", "subject", "recorded_by")
        .order_by("subject__name", "student__student_profile__user__first_name")
    )


def list_for_batches(branch_id, batch_ids):
    if not batch_ids:
        return InternalMark.objects.none()
    return (
        InternalMark.objects.filter(
            branch_id=branch_id,
            student__batch_id__in=batch_ids,
            student__status="active",
            student__is_active=True,
            is_active=True,
        )
        .select_related("student__student_profile__user", "student__batch__course", "subject", "recorded_by")
        .order_by("subject__name", "student__student_profile__user__first_name")
    )


def get_for_student_subject(branch_id, student_profile_id, subject_id) -> InternalMark | None:
    enrollment = get_student_in_branch(branch_id, student_profile_id)
    if enrollment is None:
        return None
    try:
        return InternalMark.objects.select_related(
            "student__student_profile__user", "student__batch__course", "subject", "recorded_by",
        ).get(
            branch_id=branch_id, student_id=enrollment.pk,
            subject_id=subject_id, is_active=True,
        )
    except (InternalMark.DoesNotExist, ValueError, TypeError):
        return None


def upsert(*, branch, student, subject, marks, max_marks=100,
           hard_deadline_at=None, user=None) -> InternalMark:
    obj, _ = InternalMark.objects.update_or_create(
        branch=branch, student=student, subject=subject, is_active=True,
        defaults={
            "marks": marks, "max_marks": max_marks,
            "hard_deadline_at": hard_deadline_at, "recorded_by": user, "updated_by": user,
        },
    )
    return obj
