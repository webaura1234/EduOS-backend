"""Queries — student/parent examination hub reads (all ORM here)."""

from django.utils import timezone

from apps.accounts.models.profile import StudentProfile
from apps.examinations.enums import MarksStatus
from apps.examinations.models import ExamRegistration, ExamScheduleSlot, MarksEntry, StudentResult
from apps.fees.queries.portal import guardian_portal_link


def student_profile_for_user(user_id) -> StudentProfile | None:
    try:
        return StudentProfile.objects.select_related(
            "user",
            "current_batch",
            "current_batch__course",
            "current_batch__course__department",
            "current_batch__course__department__branch",
        ).get(user_id=user_id, is_active=True)
    except (StudentProfile.DoesNotExist, ValueError, TypeError):
        return None


def student_profile_for_guardian(guardian_user_id, student_user_id) -> StudentProfile | None:
    if not guardian_portal_link(guardian_user_id, student_user_id):
        return None
    return student_profile_for_user(student_user_id)


def list_upcoming_slots_for_batch(branch_id, batch_id):
    now = timezone.now()
    return (
        ExamScheduleSlot.objects.filter(
            exam__branch_id=branch_id,
            batch_id=batch_id,
            start_at__gte=now,
            is_active=True,
            exam__is_active=True,
        )
        .select_related("exam", "subject", "batch", "room")
        .order_by("start_at")
    )


def student_exam_fees_paid(student_id) -> bool:
    return not ExamRegistration.objects.filter(
        student_id=student_id,
        is_active=True,
        fee_paid=False,
    ).exclude(exam__exam_fee_paise=0).exists()


def list_published_marks_for_student(student_id):
    return MarksEntry.objects.filter(
        student_id=student_id,
        exam__is_published=True,
        marks_status__in=[MarksStatus.SUBMITTED, MarksStatus.LOCKED],
        is_active=True,
    ).select_related("exam", "subject")


def get_slot_for_exam_subject_batch(exam_id, subject_id, batch_id):
    return (
        ExamScheduleSlot.objects.filter(
            exam_id=exam_id,
            subject_id=subject_id,
            batch_id=batch_id,
            is_active=True,
        )
        .select_related("exam", "subject")
        .first()
    )


def list_published_student_results(student_id):
    return StudentResult.objects.filter(
        student_id=student_id,
        exam__is_published=True,
        is_active=True,
    ).select_related("exam", "publication").order_by("-publication__published_at")
