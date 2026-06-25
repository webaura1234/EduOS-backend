"""Interactors — marks entry, validation, submit."""

from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.examinations.enums import MarksAuditType, MarksStatus
from apps.examinations.exceptions import (
    MarksConflictOfInterestError,
    MarksDeadlineError,
    MarksVersionConflictError,
)
from apps.examinations.helpers import (
    is_admin_role,
    is_conflict_of_interest,
    parse_marks_value,
    validate_marks_against_max,
)
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import marks as marks_q
from apps.examinations.queries import registration as reg_q
from apps.fees.queries.structure import get_student_in_branch


def _deadline_passed(exam) -> bool:
    deadline = exam.marks_deadline
    return bool(deadline and timezone.now() > deadline)


def _enforce_deadline(exam, actor, *, override: bool, reason: str = ""):
    if not _deadline_passed(exam):
        return
    if is_admin_role(actor) and override:
        return "override"
    raise MarksDeadlineError()


def _enforce_conflict(actor, student_profile, *, override: bool):
    if not is_conflict_of_interest(actor, student_profile):
        return False
    if is_admin_role(actor) and override:
        return True
    raise MarksConflictOfInterestError()


def _ensure_editable(entry, actor, *, override: bool):
    if entry.marks_status == MarksStatus.DRAFT:
        return
    if (
        entry.marks_status in (MarksStatus.SUBMITTED, MarksStatus.LOCKED)
        and is_admin_role(actor)
        and override
    ):
        return
    raise ValidationError({"marksStatus": "Marks are locked and cannot be edited."})


def serialize_marks_entry(entry, slot) -> dict:
    return {
        "id": str(entry.pk),
        "examSlotId": str(slot.pk),
        "studentId": str(entry.student.student_profile_id),
        "studentName": entry.student.user.full_name,
        "classLabel": entry.student.current_batch.name if entry.student.current_batch else "",
        "subjectName": entry.subject.name,
        "marks": marks_q.marks_value_for_response(entry),
        "maxMarks": float(slot.max_marks),
        "isAbsent": entry.is_absent,
        "marksStatus": entry.marks_status,
        "version": entry.version,
        "updatedAt": entry.updated_at.isoformat(),
    }


@transaction.atomic
def get_slot_roster(slot, *, branch_id):
    registrations = list(reg_q.list_registrations(slot.exam_id, batch_id=slot.batch_id))
    existing = {
        str(e.student_id): e
        for e in marks_q.list_marks_for_slot_by_exam_subject(
            slot.exam_id, slot.subject_id, slot.batch_id
        )
    }
    roster = []
    for reg in registrations:
        entry = existing.get(str(reg.student_id))
        roster.append(
            {
                "studentId": str(reg.student.student_profile_id),
                "studentName": reg.student.user.full_name,
                "classLabel": reg.student.current_batch.name if reg.student.current_batch else "",
                "marks": marks_q.marks_value_for_response(entry) if entry else None,
                "isAbsent": entry.is_absent if entry else False,
                "marksStatus": entry.marks_status if entry else MarksStatus.DRAFT,
                "marksEntryId": str(entry.pk) if entry else None,
                "version": entry.version if entry else None,
            }
        )
    return roster


@transaction.atomic
def bulk_save_draft_marks(
    slot,
    *,
    branch_id,
    entries: list[dict],
    actor,
    override: bool = False,
    override_reason: str = "",
):
    _enforce_deadline(slot.exam, actor, override=override, reason=override_reason)
    saved = []
    max_marks = Decimal(str(slot.max_marks))
    late_override = _deadline_passed(slot.exam) and is_admin_role(actor) and override

    for item in entries:
        student_id = item["studentId"]
        is_absent = item.get("isAbsent", False)
        marks = parse_marks_value(item.get("marks"), is_absent=is_absent)
        validate_marks_against_max(marks, max_marks=max_marks, is_absent=is_absent)

        # `student_id` is the StudentProfile id (API). Resolve to the enrollment and use
        # its id for every downstream exam-row query/write (enrollment seam, Stage 5).
        student = get_student_in_branch(branch_id, student_id)
        if not student:
            raise ValidationError({"studentId": f"Student {student_id} not found in this branch."})
        enrollment_id = student.pk
        if not reg_q.registration_exists(slot.exam_id, enrollment_id):
            raise ValidationError({"studentId": f"Student {student_id} is not registered for this exam."})

        conflict_override = _enforce_conflict(actor, student, override=override)
        existing = marks_q.get_marks_for_student(slot.exam_id, slot.subject_id, enrollment_id)
        if existing:
            _ensure_editable(existing, actor, override=override)
            if existing.marks_status != MarksStatus.DRAFT:
                if not (is_admin_role(actor) and override):
                    saved.append(serialize_marks_entry(existing, slot))
                    continue
                entry = marks_q.correct_marks_entry(
                    existing,
                    marks=marks,
                    is_absent=is_absent,
                    user=actor,
                )
                marks_q.create_marks_audit(
                    marks_entry_id=entry.pk,
                    audit_type=MarksAuditType.LATE_SUBMIT_OVERRIDE,
                    actor=actor,
                    reason=override_reason or "Post-publish mark correction",
                    metadata={"studentId": str(student_id)},
                    user=actor,
                )
                saved.append(serialize_marks_entry(entry, slot))
                continue

        entry = marks_q.upsert_marks_entry(
            exam_id=slot.exam_id,
            subject_id=slot.subject_id,
            student_id=enrollment_id,
            marks=marks,
            is_absent=is_absent,
            user=actor,
        )

        if conflict_override:
            marks_q.create_marks_audit(
                marks_entry_id=entry.pk,
                audit_type=MarksAuditType.CONFLICT_OVERRIDE,
                actor=actor,
                reason=override_reason,
                metadata={"studentId": str(student_id)},
                user=actor,
            )
        if late_override:
            marks_q.create_marks_audit(
                marks_entry_id=entry.pk,
                audit_type=MarksAuditType.LATE_SUBMIT_OVERRIDE,
                actor=actor,
                reason=override_reason,
                user=actor,
            )
        saved.append(serialize_marks_entry(entry, slot))

    return saved


@transaction.atomic
def patch_marks_entry(
    entry,
    slot,
    *,
    branch_id,
    marks_raw,
    is_absent: bool,
    expected_version: int,
    actor,
    override: bool = False,
    override_reason: str = "",
):
    _enforce_deadline(slot.exam, actor, override=override, reason=override_reason)
    _ensure_editable(entry, actor, override=override)
    conflict_override = _enforce_conflict(actor, entry.student, override=override)

    marks = parse_marks_value(marks_raw, is_absent=is_absent)
    validate_marks_against_max(marks, max_marks=Decimal(str(slot.max_marks)), is_absent=is_absent)

    updated = marks_q.update_marks_entry_versioned(
        entry.pk,
        expected_version=expected_version,
        marks=marks,
        is_absent=is_absent,
        user=actor,
    )
    if updated is None:
        current = marks_q.get_marks_entry_current(entry.pk)
        raise MarksVersionConflictError(
            current_version=current.version if current else expected_version,
            current_value=marks_q.marks_value_for_response(current) if current else None,
        )

    if conflict_override:
        marks_q.create_marks_audit(
            marks_entry_id=updated.pk,
            audit_type=MarksAuditType.CONFLICT_OVERRIDE,
            actor=actor,
            reason=override_reason,
            user=actor,
        )
    if _deadline_passed(slot.exam) and is_admin_role(actor) and override:
        marks_q.create_marks_audit(
            marks_entry_id=updated.pk,
            audit_type=MarksAuditType.LATE_SUBMIT_OVERRIDE,
            actor=actor,
            reason=override_reason,
            user=actor,
        )
    return serialize_marks_entry(updated, slot)


@transaction.atomic
def submit_slot_marks(slot, *, actor, override: bool = False, override_reason: str = ""):
    _enforce_deadline(slot.exam, actor, override=override, reason=override_reason)
    count = marks_q.submit_marks_for_slot(
        exam_id=slot.exam_id,
        subject_id=slot.subject_id,
        batch_id=slot.batch_id,
        user=actor,
    )
    if count == 0:
        raise ValidationError({"entries": "No draft marks to submit for this slot."})

    if _deadline_passed(slot.exam) and is_admin_role(actor) and override:
        for entry in marks_q.list_marks_for_slot_by_exam_subject(
            slot.exam_id, slot.subject_id, slot.batch_id
        ):
            if entry.marks_status == MarksStatus.SUBMITTED:
                marks_q.create_marks_audit(
                    marks_entry_id=entry.pk,
                    audit_type=MarksAuditType.LATE_SUBMIT_OVERRIDE,
                    actor=actor,
                    reason=override_reason,
                    metadata={"action": "submit"},
                    user=actor,
                )
    return count
