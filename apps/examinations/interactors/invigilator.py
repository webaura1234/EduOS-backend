"""Interactors — invigilator duty assignment."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.academics.helpers import require_faculty
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import invigilator as inv_q


def _faculty_available(faculty_id, slot) -> bool:
    for duty in inv_q.faculty_duties_for_overlap_check(faculty_id, exclude_slot_id=slot.pk):
        if inv_q.slots_overlap(slot, duty.schedule_slot):
            return False
    return True


@transaction.atomic
def assign_invigilator_manual(*, exam, slot, branch, tenant_id, faculty_id, user=None) -> dict:
    if slot.exam_id != exam.pk:
        raise ValidationError({"examSlotId": "Schedule slot does not belong to this exam."})
    faculty = require_faculty(tenant_id, faculty_id)
    if faculty.branch_id != branch.pk:
        raise ValidationError({"facultyId": "Faculty must belong to this branch."})
    if not _faculty_available(faculty.pk, slot):
        raise ValidationError({"facultyId": "Faculty has a conflicting invigilation duty at this time."})

    inv_q.soft_delete_duties_for_slot(slot.pk, user=user)
    inv_q.create_duty(schedule_slot_id=slot.pk, faculty_id=faculty.pk, user=user)
    return {
        "examSlotId": str(slot.pk),
        "facultyId": str(faculty.pk),
        "facultyName": faculty.full_name,
        "assignedAt": timezone.now().isoformat(),
        "assignedBy": "manual",
    }


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
        inv_q.soft_delete_duties_for_slot(slot.pk, user=user)
        chosen = next((f for f in faculty_list if _faculty_available(f.pk, slot)), None)
        if not chosen:
            raise ValidationError(
                {"faculty": f"No available faculty for slot {slot.pk} ({slot.start_at})."}
            )
        inv_q.create_duty(schedule_slot_id=slot.pk, faculty_id=chosen.pk, user=user)
        assignments.append(
            {
                "examSlotId": str(slot.pk),
                "facultyId": str(chosen.pk),
                "facultyName": chosen.full_name,
                "assignedAt": timezone.now().isoformat(),
                "assignedBy": "auto",
            }
        )
    return assignments
