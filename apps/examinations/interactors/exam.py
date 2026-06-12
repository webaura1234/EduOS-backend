"""Interactors — grade scales, exams, and schedule slots."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.academics.helpers import check_version, is_college
from apps.academics.queries import holiday as hol_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import timetable as tt_q
from apps.examinations.helpers import combine_datetime, parse_time, validate_bands
from apps.examinations.queries import exam as exam_q


def _resolve_slot_times(*, date, start_time: str, end_time: str):
    start_at = combine_datetime(date, parse_time(start_time, field="startTime"))
    end_at = combine_datetime(date, parse_time(end_time, field="endTime"))
    if end_at <= start_at:
        raise ValidationError({"endTime": "End time must be after start time."})
    return start_at, end_at


def _validate_schedule_refs(branch_id, *, batch_id, subject_id, room_id):
    batch = struct_q.get_batch(branch_id, batch_id)
    if not batch:
        raise ValidationError({"classSectionId": "Batch not found in this branch."})
    subject = curr_q.get_subject(branch_id, subject_id)
    if not subject:
        raise ValidationError({"subjectId": "Subject not found in this branch."})
    room = tt_q.get_room(branch_id, room_id)
    if not room:
        raise ValidationError({"roomId": "Room not found in this branch."})
    return batch, subject, room


def _check_clashes(branch_id, *, room_id, batch_id, start_at, end_at, exclude_id=None):
    clashes = exam_q.find_slot_clashes(
        branch_id=branch_id,
        room_id=room_id,
        batch_id=batch_id,
        start_at=start_at,
        end_at=end_at,
        exclude_id=exclude_id,
    )
    if clashes:
        raise ValidationError({"clashes": [c.to_dict() for c in clashes]})


def _holiday_warnings(branch_id, date) -> list[dict]:
    if hol_q.is_holiday(branch_id, date):
        return [{"type": "holiday", "message": f"{date.isoformat()} is a holiday."}]
    return []


@transaction.atomic
def create_grade_scale(branch_id, *, course_id, name, bands, grace_marks_max=0, is_default=False, tenant=None, user=None):
    validate_bands(bands)
    course = struct_q.get_course(branch_id, course_id)
    if not course:
        raise ValidationError({"courseId": "Course not found in this branch."})
    if tenant and not is_college(tenant) and grace_marks_max:
        raise ValidationError({"graceMarksMax": "Grace marks are college-only."})
    if exam_q.grade_scale_name_exists(branch_id, course_id, name):
        raise ValidationError({"name": "A grade scale with this name already exists for the course."})
    return exam_q.create_grade_scale(
        branch_id,
        course_id=course_id,
        name=name,
        bands=bands,
        grace_marks_max=grace_marks_max,
        is_default=is_default,
        user=user,
    )


@transaction.atomic
def update_grade_scale(scale, *, fields: dict, tenant=None, user=None):
    check_version(scale, fields.pop("version", None))
    if "bands" in fields:
        validate_bands(fields["bands"])
    if "grace_marks_max" in fields and tenant and not is_college(tenant) and fields["grace_marks_max"]:
        raise ValidationError({"graceMarksMax": "Grace marks are college-only."})
    name = fields.get("name", scale.name)
    course_id = fields.get("course_id", scale.course_id)
    if exam_q.grade_scale_name_exists(scale.branch_id, course_id, name, exclude_id=scale.pk):
        raise ValidationError({"name": "A grade scale with this name already exists for the course."})
    return exam_q.update_grade_scale(scale, fields, user=user)


@transaction.atomic
def create_exam(branch_id, *, academic_period_id, name, exam_type, exam_fee_paise=0, marks_deadline=None, user=None):
    if not name or not name.strip():
        raise ValidationError({"name": "Exam name is required."})
    period = exam_q.get_period_in_branch(branch_id, academic_period_id)
    if not period:
        raise ValidationError({"academicPeriodId": "Academic period not found in this branch."})
    return exam_q.create_exam(
        branch_id,
        academic_period_id=academic_period_id,
        name=name.strip(),
        exam_type=exam_type,
        exam_fee_paise=exam_fee_paise,
        marks_deadline=marks_deadline,
        user=user,
    )


@transaction.atomic
def update_exam(exam, *, fields: dict, user=None):
    check_version(exam, fields.pop("version", None))
    if "name" in fields and (not fields["name"] or not str(fields["name"]).strip()):
        raise ValidationError({"name": "Exam name cannot be blank."})
    if "academic_period_id" in fields:
        period = exam_q.get_period_in_branch(exam.branch_id, fields["academic_period_id"])
        if not period:
            raise ValidationError({"academicPeriodId": "Academic period not found in this branch."})
    return exam_q.update_exam(exam, fields, user=user)


@transaction.atomic
def create_schedule_slot(
    exam,
    *,
    branch_id,
    class_section_id,
    subject_id,
    date,
    start_time,
    end_time,
    room_id,
    max_marks=None,
    override=False,
    user=None,
):
    batch, subject, room = _validate_schedule_refs(
        branch_id, batch_id=class_section_id, subject_id=subject_id, room_id=room_id
    )
    start_at, end_at = _resolve_slot_times(date=date, start_time=start_time, end_time=end_time)
    warnings = _holiday_warnings(branch_id, date)
    if warnings and not override:
        return None, warnings, True

    _check_clashes(
        branch_id,
        room_id=room_id,
        batch_id=class_section_id,
        start_at=start_at,
        end_at=end_at,
    )
    slot = exam_q.create_schedule_slot(
        exam.pk,
        subject_id=subject_id,
        batch_id=class_section_id,
        room_id=room_id,
        start_at=start_at,
        end_at=end_at,
        max_marks=max_marks if max_marks is not None else subject.max_marks,
        max_capacity=room.capacity,
        user=user,
    )
    return slot, warnings, False


@transaction.atomic
def update_schedule_slot(
    slot,
    *,
    branch_id,
    fields: dict,
    override=False,
    user=None,
):
    check_version(slot, fields.pop("version", None))
    date = fields.pop("date", None)
    start_time = fields.pop("start_time", None)
    end_time = fields.pop("end_time", None)

    batch_id = fields.get("batch_id", slot.batch_id)
    subject_id = fields.get("subject_id", slot.subject_id)
    room_id = fields.get("room_id", slot.room_id)

    if date or start_time or end_time:
        local = slot.start_at
        if date is None:
            date = local.date()
        if start_time is None:
            start_time = local.strftime("%H:%M")
        if end_time is None:
            end_time = slot.end_at.strftime("%H:%M")
        start_at, end_at = _resolve_slot_times(date=date, start_time=start_time, end_time=end_time)
        fields["start_at"] = start_at
        fields["end_at"] = end_at
    else:
        start_at = slot.start_at
        end_at = slot.end_at
        date = start_at.date()

    if any(k in fields for k in ("batch_id", "subject_id", "room_id")):
        _validate_schedule_refs(branch_id, batch_id=batch_id, subject_id=subject_id, room_id=room_id)

    warnings = _holiday_warnings(branch_id, date)
    if warnings and not override:
        return None, warnings, True

    _check_clashes(
        branch_id,
        room_id=room_id,
        batch_id=batch_id,
        start_at=fields.get("start_at", start_at),
        end_at=fields.get("end_at", end_at),
        exclude_id=slot.pk,
    )
    slot = exam_q.update_schedule_slot(slot, fields, user=user)
    return slot, warnings, False
