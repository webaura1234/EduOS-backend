"""Queries — invigilator duties (all ORM here)."""

from apps.accounts.models.user import Role, User
from apps.examinations.models import ExamScheduleSlot, InvigilatorDuty


def list_faculty_in_branch(tenant_id, branch_id):
    return User.objects.filter(
        tenant_id=tenant_id,
        branch_id=branch_id,
        role=Role.FACULTY,
        is_active=True,
    ).order_by("first_name", "last_name")


def list_duties_for_exam(exam_id):
    return (
        InvigilatorDuty.objects.filter(schedule_slot__exam_id=exam_id, is_active=True)
        .select_related("schedule_slot", "faculty")
        .order_by("schedule_slot__start_at")
    )


def list_duties_for_slot(schedule_slot_id):
    return (
        InvigilatorDuty.objects.filter(schedule_slot_id=schedule_slot_id, is_active=True)
        .select_related("faculty")
    )


def count_duties_for_slot(schedule_slot_id) -> int:
    return InvigilatorDuty.objects.filter(schedule_slot_id=schedule_slot_id, is_active=True).count()


def duty_exists(schedule_slot_id, faculty_id) -> bool:
    return InvigilatorDuty.objects.filter(
        schedule_slot_id=schedule_slot_id,
        faculty_id=faculty_id,
        is_active=True,
    ).exists()


def clear_duties_for_slot(schedule_slot_id):
    """Hard-delete prior duties so unique constraints allow reassignment."""
    InvigilatorDuty.objects.filter(schedule_slot_id=schedule_slot_id).delete()


def soft_delete_duties_for_slot(schedule_slot_id, user=None):
    clear_duties_for_slot(schedule_slot_id)


def soft_delete_duty(schedule_slot_id, faculty_id, user=None):
    duty = InvigilatorDuty.objects.filter(
        schedule_slot_id=schedule_slot_id,
        faculty_id=faculty_id,
        is_active=True,
    ).first()
    if duty:
        duty.soft_delete(user)


def create_duty(*, schedule_slot_id, faculty_id, user=None) -> InvigilatorDuty:
    return InvigilatorDuty.objects.create(
        schedule_slot_id=schedule_slot_id,
        faculty_id=faculty_id,
        created_by=user,
        updated_by=user,
    )


def list_for_faculty(branch_id, faculty_id):
    """Invigilation duties assigned to a faculty member, scoped to the branch."""
    return (
        InvigilatorDuty.objects.filter(
            faculty_id=faculty_id, is_active=True,
            schedule_slot__exam__branch_id=branch_id,
        )
        .select_related("schedule_slot__exam", "schedule_slot__subject", "schedule_slot__batch", "faculty")
        .order_by("schedule_slot__start_at")
    )


def faculty_duties_for_overlap_check(faculty_id, *, exclude_slot_id=None):
    qs = InvigilatorDuty.objects.filter(faculty_id=faculty_id, is_active=True).select_related(
        "schedule_slot"
    )
    if exclude_slot_id:
        qs = qs.exclude(schedule_slot_id=exclude_slot_id)
    return qs


def slots_overlap(a: ExamScheduleSlot, b: ExamScheduleSlot) -> bool:
    return a.start_at < b.end_at and a.end_at > b.start_at
