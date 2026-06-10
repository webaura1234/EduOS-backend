"""Interactors — Timetable infrastructure and clash detection."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.academics.dtos import TimetableClashDTO
from apps.academics.helpers import check_version, get_faculty_user
from apps.academics.models import TimetableEntryStatus
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import timetable as tt_q


@transaction.atomic
def create_timetable(branch_id, *, batch_id, academic_period_id, user=None):
    """Create (or return the existing) timetable for a batch + academic period."""
    batch = struct_q.get_batch(branch_id, batch_id)
    if not batch:
        raise ValidationError({"batchId": "Batch not found in this branch."})
    if batch.academic_year.is_frozen:
        raise ValidationError("Cannot create a timetable in a frozen academic year.")
    period = cal_q.get_period(batch.academic_year_id, academic_period_id)
    if not period:
        raise ValidationError(
            {"academicPeriodId": "Academic period not found within this batch's academic year."}
        )
    return tt_q.get_or_create_timetable(batch=batch, academic_period=period, user=user)


def detect_clashes(
    branch_id,
    *,
    day_of_week,
    period_slot_id,
    faculty_id=None,
    room_id=None,
    exclude_entry_id=None,
) -> list[TimetableClashDTO]:
    clashes = []
    raw = tt_q.find_clashing_entries(
        branch_id,
        day_of_week=day_of_week,
        period_slot_id=period_slot_id,
        faculty_id=faculty_id,
        room_id=room_id,
        exclude_entry_id=exclude_entry_id,
    )
    for clash_type, qs in raw:
        ids = [str(e.pk) for e in qs]
        if clash_type == "faculty":
            msg = "Faculty is already assigned to another subject in this time slot."
        else:
            msg = "Room is already booked for another class in this time slot."
        clashes.append(TimetableClashDTO(type=clash_type, message=msg, entry_ids=ids))
    return clashes


def list_all_clashes(branch_id) -> list[TimetableClashDTO]:
    entries = list(tt_q.list_active_entries_for_branch(branch_id))
    seen = set()
    all_clashes: list[TimetableClashDTO] = []
    for entry in entries:
        if entry.status != TimetableEntryStatus.ACTIVE:
            continue
        hits = detect_clashes(
            branch_id,
            day_of_week=entry.day_of_week,
            period_slot_id=entry.period_slot_id,
            faculty_id=entry.faculty_id,
            room_id=entry.room_id,
            exclude_entry_id=entry.pk,
        )
        for c in hits:
            key = (c.type, tuple(sorted(c.entry_ids + [str(entry.pk)])))
            if key not in seen:
                seen.add(key)
                all_clashes.append(c)
    return all_clashes


def _validate_clashes(branch_id, *, day_of_week, period_slot_id, faculty_id, room_id, exclude_entry_id=None):
    if faculty_id or room_id:
        clashes = detect_clashes(
            branch_id,
            day_of_week=day_of_week,
            period_slot_id=period_slot_id,
            faculty_id=faculty_id,
            room_id=room_id,
            exclude_entry_id=exclude_entry_id,
        )
        if clashes:
            raise ValidationError({"clashes": [c.to_dict() for c in clashes]})


@transaction.atomic
def create_period_slot(branch_id, *, name, sequence, start_time, end_time, user=None):
    if tt_q.period_slot_sequence_exists(branch_id, sequence):
        raise ValidationError({"sequence": "A period slot with this sequence already exists."})
    if end_time <= start_time:
        raise ValidationError({"endTime": "End time must be after start time."})
    return tt_q.create_period_slot(
        branch_id, name=name, sequence=sequence, start_time=start_time, end_time=end_time, user=user
    )


@transaction.atomic
def update_period_slot(slot, *, fields: dict, user=None):
    check_version(slot, fields.pop("version", None))
    seq = fields.get("sequence", slot.sequence)
    if tt_q.period_slot_sequence_exists(slot.branch_id, seq, exclude_id=slot.pk):
        raise ValidationError({"sequence": "A period slot with this sequence already exists."})
    return tt_q.update_period_slot(slot, fields, user=user)


@transaction.atomic
def delete_period_slot(slot, user=None):
    if tt_q.period_slot_in_use(slot.pk):
        raise ValidationError("Cannot delete a period slot referenced by timetable entries.")
    return tt_q.soft_delete_period_slot(slot, user=user)


@transaction.atomic
def create_room(branch_id, *, name, code, capacity, is_lab, user=None):
    if tt_q.room_name_exists(branch_id, name):
        raise ValidationError({"name": "A room with this name already exists."})
    return tt_q.create_room(
        branch_id, name=name, code=code, capacity=capacity, is_lab=is_lab, user=user
    )


@transaction.atomic
def update_room(room, *, fields: dict, user=None):
    check_version(room, fields.pop("version", None))
    name = fields.get("name", room.name)
    if tt_q.room_name_exists(room.branch_id, name, exclude_id=room.pk):
        raise ValidationError({"name": "A room with this name already exists."})
    return tt_q.update_room(room, fields, user=user)


@transaction.atomic
def delete_room(room, user=None):
    return tt_q.soft_delete_room(room, user=user)


@transaction.atomic
def create_timetable_entry(
    branch_id, tenant_id, timetable, *, batch_subject_id, period_slot_id,
    day_of_week, faculty_id=None, room_id=None, status=TimetableEntryStatus.ACTIVE, user=None,
):
    if timetable.batch.academic_year.is_frozen:
        raise ValidationError("Cannot modify timetable in a frozen academic year.")
    bs = curr_q.get_batch_subject(branch_id, batch_subject_id)
    if not bs or bs.batch_id != timetable.batch_id:
        raise ValidationError({"batchSubjectId": "Invalid batch subject for this timetable."})
    slot = tt_q.get_period_slot(branch_id, period_slot_id)
    if not slot:
        raise ValidationError({"periodSlotId": "Period slot not found."})
    if faculty_id:
        if not get_faculty_user(tenant_id, faculty_id):
            raise ValidationError({"facultyId": "Faculty not found."})
    if room_id:
        if not tt_q.get_room(branch_id, room_id):
            raise ValidationError({"roomId": "Room not found."})
    if status == TimetableEntryStatus.ACTIVE:
        _validate_clashes(
            branch_id, day_of_week=day_of_week, period_slot_id=period_slot_id,
            faculty_id=faculty_id, room_id=room_id,
        )
    return tt_q.create_timetable_entry(
        timetable=timetable, batch_subject=bs, period_slot=slot,
        day_of_week=day_of_week, faculty_id=faculty_id, room_id=room_id,
        status=status, user=user,
    )


@transaction.atomic
def update_timetable_entry(branch_id, tenant_id, entry, *, fields: dict, user=None):
    if entry.timetable.batch.academic_year.is_frozen:
        raise ValidationError("Cannot modify timetable in a frozen academic year.")
    check_version(entry, fields.pop("version", None))
    day = fields.get("day_of_week", entry.day_of_week)
    slot_id = fields.get("period_slot_id", entry.period_slot_id)
    faculty_id = fields.get("faculty_id", entry.faculty_id) if "faculty_id" in fields else entry.faculty_id
    room_id = fields.get("room_id", entry.room_id) if "room_id" in fields else entry.room_id
    status = fields.get("status", entry.status)
    if "faculty_id" in fields and fields["faculty_id"]:
        if not get_faculty_user(tenant_id, fields["faculty_id"]):
            raise ValidationError({"facultyId": "Faculty not found."})
    if "room_id" in fields and fields["room_id"]:
        if not tt_q.get_room(branch_id, fields["room_id"]):
            raise ValidationError({"roomId": "Room not found."})
    if status == TimetableEntryStatus.ACTIVE:
        _validate_clashes(
            branch_id, day_of_week=day, period_slot_id=slot_id,
            faculty_id=faculty_id, room_id=room_id, exclude_entry_id=entry.pk,
        )
    return tt_q.update_timetable_entry(entry, fields, user=user)


@transaction.atomic
def delete_timetable_entry(entry, user=None):
    if entry.timetable.batch.academic_year.is_frozen:
        raise ValidationError("Cannot modify timetable in a frozen academic year.")
    return tt_q.soft_delete_timetable_entry(entry, user=user)


@transaction.atomic
def publish_timetable(timetable, *, user=None):
    check_version(timetable, None)
    return tt_q.publish_timetable(timetable, user=user)
