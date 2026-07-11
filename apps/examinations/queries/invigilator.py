"""Queries — invigilator duties (all ORM here)."""

from django.db import IntegrityError, transaction

from apps.accounts.models.user import Role, User
from apps.examinations.models import ExamScheduleSlot, InvigilatorDuty


def list_faculty_in_branch(tenant_id, branch_id):
    """Faculty eligible for invigilation duty in this branch.

    Excludes deactivated accounts and accounts that have not finished activation
    (invite pending / forced password reset).
    """
    return User.objects.filter(
        tenant_id=tenant_id,
        branch_id=branch_id,
        role=Role.FACULTY,
        is_active=True,
        must_change_password=False,
    ).order_by("first_name", "last_name")


def faculty_options_for_branch(tenant_id, branch_id) -> list[dict]:
    """Dropdown options for invigilator assignment (eligible faculty only)."""
    return [
        {"userId": str(u.id), "name": u.full_name}
        for u in list_faculty_in_branch(tenant_id, branch_id)
    ]


def list_duties_for_exam(exam_id):
    return (
        InvigilatorDuty.objects.filter(schedule_slot__exam_id=exam_id, is_active=True)
        .select_related("schedule_slot", "faculty")
        .order_by("schedule_slot__start_at")
    )


def list_duties_for_exams(exam_ids):
    """Batch variant of ``list_duties_for_exam`` for many exams in one query —
    the admin overview screen needs every exam's duties at once."""
    return (
        InvigilatorDuty.objects.filter(schedule_slot__exam_id__in=exam_ids, is_active=True)
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
    """Hard-delete all duties for a slot (used by auto-assign before rebuilding)."""
    InvigilatorDuty.objects.filter(schedule_slot_id=schedule_slot_id).delete()


def soft_delete_duties_for_slot(schedule_slot_id, user=None):
    """Clear slot duties before auto-reassign. Hard-delete avoids unique collisions."""
    clear_duties_for_slot(schedule_slot_id)


def soft_delete_duty(schedule_slot_id, faculty_id, user=None):
    duty = InvigilatorDuty.objects.filter(
        schedule_slot_id=schedule_slot_id,
        faculty_id=faculty_id,
        is_active=True,
    ).first()
    if duty:
        duty.soft_delete(user)


def _reactivate_duty(duty: InvigilatorDuty, user=None) -> InvigilatorDuty:
    duty.is_active = True
    duty.version += 1
    update_fields = ["is_active", "version", "updated_at"]
    if user is not None:
        duty.updated_by = user
        update_fields.append("updated_by")
    duty.save(update_fields=update_fields)
    return duty


def create_duty(*, schedule_slot_id, faculty_id, user=None) -> InvigilatorDuty:
    """
    Create (or reactivate) an invigilator duty.

    Soft-remove leaves an inactive row; uniqueness is only on active rows, but
    reactivating the same row is preferred over inserting a duplicate inactive.
    """
    with transaction.atomic():
        existing = (
            InvigilatorDuty.objects.select_for_update()
            .filter(schedule_slot_id=schedule_slot_id, faculty_id=faculty_id)
            .order_by("-is_active", "-updated_at")
            .first()
        )
        if existing:
            if existing.is_active:
                return existing
            return _reactivate_duty(existing, user=user)

        try:
            return InvigilatorDuty.objects.create(
                schedule_slot_id=schedule_slot_id,
                faculty_id=faculty_id,
                created_by=user,
                updated_by=user,
            )
        except IntegrityError:
            # Concurrent create / pre-migration unique constraint — resolve safely.
            raced = (
                InvigilatorDuty.objects.select_for_update()
                .filter(schedule_slot_id=schedule_slot_id, faculty_id=faculty_id)
                .first()
            )
            if raced is None:
                raise
            if raced.is_active:
                return raced
            return _reactivate_duty(raced, user=user)


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
