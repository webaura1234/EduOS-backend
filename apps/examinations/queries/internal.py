"""Queries — InternalMark (internal/continuous assessment)."""

from apps.examinations.models import InternalMark


def list_recorded_by(branch_id, faculty_user_id):
    return (
        InternalMark.objects.filter(
            branch_id=branch_id, recorded_by_id=faculty_user_id, is_active=True,
        )
        .select_related("student_profile__user", "subject")
        .order_by("subject__name", "student_profile__user__first_name")
    )


def get_for_student_subject(branch_id, student_profile_id, subject_id) -> InternalMark | None:
    try:
        return InternalMark.objects.select_related("student_profile__user", "subject").get(
            branch_id=branch_id, student_profile_id=student_profile_id,
            subject_id=subject_id, is_active=True,
        )
    except (InternalMark.DoesNotExist, ValueError, TypeError):
        return None


def upsert(*, branch, student_profile, subject, marks, max_marks=100,
           hard_deadline_at=None, user=None) -> InternalMark:
    obj, _ = InternalMark.objects.update_or_create(
        branch=branch, student_profile=student_profile, subject=subject, is_active=True,
        defaults={
            "marks": marks, "max_marks": max_marks,
            "hard_deadline_at": hard_deadline_at, "recorded_by": user, "updated_by": user,
        },
    )
    return obj
