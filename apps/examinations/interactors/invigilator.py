"""Interactors — invigilator duty assignment."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.academics.helpers import require_faculty
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import invigilator as inv_q


def _faculty_available_for_slot(faculty_id, slot, *, exclude_faculty_ids=None) -> bool:
    exclude_faculty_ids = exclude_faculty_ids or set()
    if faculty_id in exclude_faculty_ids:
        return False
    for duty in inv_q.faculty_duties_for_overlap_check(faculty_id, exclude_slot_id=slot.pk):
        if inv_q.slots_overlap(slot, duty.schedule_slot):
            return False
    return True


def _serialize_assignment(slot, faculty, *, assigned_by: str) -> dict:
    return {
        "examSlotId": str(slot.pk),
        "facultyId": str(faculty.pk),
        "facultyName": faculty.full_name,
        "assignedAt": timezone.now().isoformat(),
        "assignedBy": assigned_by,
    }


def _resolve_faculty(*, tenant_id, faculty_id, branch):
    faculty = require_faculty(tenant_id, faculty_id)
    if faculty.branch_id != branch.pk:
        raise ValidationError({"facultyId": "Faculty must belong to this branch."})
    return faculty


def _check_slot_belongs_to_exam(exam, slot):
    if slot.exam_id != exam.pk:
        raise ValidationError({"examSlotId": "Schedule slot does not belong to this exam."})


@transaction.atomic
def add_invigilator(*, exam, slot, branch, tenant_id, faculty_id, user=None) -> dict:
    _check_slot_belongs_to_exam(exam, slot)
    faculty = _resolve_faculty(tenant_id=tenant_id, faculty_id=faculty_id, branch=branch)

    if inv_q.duty_exists(slot.pk, faculty.pk):
        raise ValidationError({"facultyId": "Faculty already assigned to this slot."})

    assigned = inv_q.count_duties_for_slot(slot.pk)
    if assigned >= slot.required_invigilators:
        raise ValidationError(
            {"facultyId": f"Slot already has {slot.required_invigilators} invigilators."}
        )

    assigned_ids = {d.faculty_id for d in inv_q.list_duties_for_slot(slot.pk)}
    if not _faculty_available_for_slot(faculty.pk, slot, exclude_faculty_ids=assigned_ids):
        raise ValidationError({"facultyId": "Faculty has a conflicting invigilation duty at this time."})

    inv_q.create_duty(schedule_slot_id=slot.pk, faculty_id=faculty.pk, user=user)
    return _serialize_assignment(slot, faculty, assigned_by="manual")


@transaction.atomic
def replace_invigilator(
    *, exam, slot, branch, tenant_id, faculty_id, replace_faculty_id, user=None
) -> dict:
    _check_slot_belongs_to_exam(exam, slot)
    if not replace_faculty_id:
        raise ValidationError({"replaceFacultyId": "replaceFacultyId is required for replace mode."})

    if not inv_q.duty_exists(slot.pk, replace_faculty_id):
        raise ValidationError({"replaceFacultyId": "Faculty not assigned to this slot."})

    new_faculty = _resolve_faculty(tenant_id=tenant_id, faculty_id=faculty_id, branch=branch)
    if str(new_faculty.pk) == str(replace_faculty_id):
        raise ValidationError({"facultyId": "Replacement faculty must be different."})

    if inv_q.duty_exists(slot.pk, new_faculty.pk):
        raise ValidationError({"facultyId": "Faculty already assigned to this slot."})

    assigned_ids = {
        d.faculty_id
        for d in inv_q.list_duties_for_slot(slot.pk)
        if d.faculty_id != replace_faculty_id
    }
    if not _faculty_available_for_slot(new_faculty.pk, slot, exclude_faculty_ids=assigned_ids):
        raise ValidationError({"facultyId": "Faculty has a conflicting invigilation duty at this time."})

    inv_q.soft_delete_duty(slot.pk, replace_faculty_id, user=user)
    inv_q.create_duty(schedule_slot_id=slot.pk, faculty_id=new_faculty.pk, user=user)
    return _serialize_assignment(slot, new_faculty, assigned_by="manual")


@transaction.atomic
def remove_invigilator(*, exam, slot, branch, tenant_id, faculty_id, user=None) -> None:
    _check_slot_belongs_to_exam(exam, slot)
    _resolve_faculty(tenant_id=tenant_id, faculty_id=faculty_id, branch=branch)
    if not inv_q.duty_exists(slot.pk, faculty_id):
        raise ValidationError({"facultyId": "Faculty not assigned to this slot."})
    inv_q.soft_delete_duty(slot.pk, faculty_id, user=user)


@transaction.atomic
def assign_invigilator_manual(*, exam, slot, branch, tenant_id, faculty_id, user=None) -> dict:
    """Backward-compatible add (does not clear existing duties)."""
    return add_invigilator(
        exam=exam,
        slot=slot,
        branch=branch,
        tenant_id=tenant_id,
        faculty_id=faculty_id,
        user=user,
    )


def _assign_slot_invigilators(*, slot, faculty_list, user=None) -> list[dict]:
    inv_q.soft_delete_duties_for_slot(slot.pk, user=user)
    required = slot.required_invigilators
    chosen = []
    assigned_ids = set()

    for faculty in faculty_list:
        if len(chosen) >= required:
            break
        if faculty.pk in assigned_ids:
            continue
        if not _faculty_available_for_slot(faculty.pk, slot, exclude_faculty_ids=assigned_ids):
            continue
        inv_q.create_duty(schedule_slot_id=slot.pk, faculty_id=faculty.pk, user=user)
        chosen.append(_serialize_assignment(slot, faculty, assigned_by="auto"))
        assigned_ids.add(faculty.pk)

    if len(chosen) < required:
        raise ValidationError(
            {
                "faculty": (
                    f"No available faculty for slot {slot.pk} "
                    f"({slot.start_at:%Y-%m-%d %H:%M}); need {required}, found {len(chosen)}."
                )
            }
        )
    return chosen


@transaction.atomic
def auto_assign_invigilators(exam, *, branch, tenant_id, user=None) -> list[dict]:
    slots = list(exam_q.list_schedule_slots(exam.pk))
    if not slots:
        raise ValidationError({"examId": "No schedule slots to assign invigilators for."})

    faculty_list = list(inv_q.list_faculty_in_branch(tenant_id, branch.pk))
    if not faculty_list:
        raise ValidationError({"faculty": "No faculty available in this branch."})

    assignments = []
    for slot in slots:
        assignments.extend(_assign_slot_invigilators(slot=slot, faculty_list=faculty_list, user=user))
    return assignments


def list_invigilation_for_exam(exam_id) -> list[dict]:
    duties = inv_q.list_duties_for_exam(exam_id)
    return [
        {
            "examSlotId": str(d.schedule_slot_id),
            "facultyId": str(d.faculty_id),
            "facultyName": d.faculty.full_name,
            "assignedAt": d.created_at.isoformat(),
            "assignedBy": "manual",
        }
        for d in duties
    ]
