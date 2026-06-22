"""Queries — PeriodSlot, Room, Timetable, TimetableEntry."""

from apps.academics.models import PeriodSlot, Room, Timetable, TimetableEntry, TimetableEntryStatus


# ── PeriodSlot ────────────────────────────────────────────────────────────────
def list_period_slots(branch_id):
    return PeriodSlot.objects.filter(branch_id=branch_id, is_active=True).order_by("sequence")


def get_period_slot(branch_id, slot_id) -> PeriodSlot | None:
    try:
        return PeriodSlot.objects.get(branch_id=branch_id, pk=slot_id, is_active=True)
    except (PeriodSlot.DoesNotExist, ValueError, TypeError):
        return None


def period_slot_sequence_exists(branch_id, sequence, exclude_id=None) -> bool:
    qs = PeriodSlot.objects.filter(branch_id=branch_id, sequence=sequence, is_active=True)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def period_slot_in_use(slot_id) -> bool:
    return TimetableEntry.objects.filter(period_slot_id=slot_id, is_active=True).exists()


def create_period_slot(branch_id, *, name, sequence, start_time, end_time, user=None) -> PeriodSlot:
    return PeriodSlot.objects.create(
        branch_id=branch_id,
        name=name,
        sequence=sequence,
        start_time=start_time,
        end_time=end_time,
        created_by=user,
        updated_by=user,
    )


def update_period_slot(slot: PeriodSlot, fields: dict, user=None) -> PeriodSlot:
    for k, v in fields.items():
        setattr(slot, k, v)
    if fields:
        slot.version += 1
        if user:
            slot.updated_by = user
        slot.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return slot


def soft_delete_period_slot(slot: PeriodSlot, user=None) -> PeriodSlot:
    slot.soft_delete(user)
    slot.version += 1
    slot.save(update_fields=["version", "updated_at"])
    return slot


# ── Room ──────────────────────────────────────────────────────────────────────
def list_rooms(branch_id):
    return Room.objects.filter(branch_id=branch_id, is_active=True).order_by("name")


def get_room(branch_id, room_id) -> Room | None:
    try:
        return Room.objects.get(branch_id=branch_id, pk=room_id, is_active=True)
    except (Room.DoesNotExist, ValueError, TypeError):
        return None


def room_name_exists(branch_id, name, exclude_id=None) -> bool:
    qs = Room.objects.filter(branch_id=branch_id, name__iexact=name, is_active=True)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def create_room(branch_id, *, name, code="", capacity=40, is_lab=False, user=None) -> Room:
    return Room.objects.create(
        branch_id=branch_id,
        name=name,
        code=code,
        capacity=capacity,
        is_lab=is_lab,
        created_by=user,
        updated_by=user,
    )


def update_room(room: Room, fields: dict, user=None) -> Room:
    for k, v in fields.items():
        setattr(room, k, v)
    if fields:
        room.version += 1
        if user:
            room.updated_by = user
        room.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return room


def soft_delete_room(room: Room, user=None) -> Room:
    room.soft_delete(user)
    room.version += 1
    room.save(update_fields=["version", "updated_at"])
    return room


# ── Timetable ─────────────────────────────────────────────────────────────────
def list_timetables(branch_id, *, batch_id=None, academic_period_id=None):
    qs = Timetable.objects.filter(
        batch__course__department__branch_id=branch_id, is_active=True
    ).select_related("batch", "academic_period")
    if batch_id:
        qs = qs.filter(batch_id=batch_id)
    if academic_period_id:
        qs = qs.filter(academic_period_id=academic_period_id)
    return qs


def get_timetable(branch_id, timetable_id) -> Timetable | None:
    try:
        return Timetable.objects.select_related("batch", "academic_period").get(
            batch__course__department__branch_id=branch_id, pk=timetable_id, is_active=True
        )
    except (Timetable.DoesNotExist, ValueError, TypeError):
        return None


def batch_has_active_timetable_entries(batch_id) -> bool:
    return TimetableEntry.objects.filter(
        timetable__batch_id=batch_id,
        status=TimetableEntryStatus.ACTIVE,
        is_active=True,
    ).exists()


def get_or_create_timetable(*, batch, academic_period, user=None) -> Timetable:
    tt, created = Timetable.objects.get_or_create(
        batch=batch,
        academic_period=academic_period,
        defaults={"created_by": user, "updated_by": user},
    )
    return tt


def publish_timetable(timetable: Timetable, user=None) -> Timetable:
    timetable.is_published = True
    timetable.version += 1
    if user:
        timetable.updated_by = user
    timetable.save(update_fields=["is_published", "version", "updated_by", "updated_at"])
    return timetable


# ── TimetableEntry ────────────────────────────────────────────────────────────
def list_timetable_entries(timetable_id):
    return TimetableEntry.objects.filter(timetable_id=timetable_id, is_active=True).select_related(
        "batch_subject", "period_slot", "faculty", "room"
    )


def get_timetable_entry(branch_id, entry_id) -> TimetableEntry | None:
    try:
        return TimetableEntry.objects.select_related(
            "timetable", "batch_subject", "period_slot", "faculty", "room"
        ).get(
            timetable__batch__course__department__branch_id=branch_id,
            pk=entry_id,
            is_active=True,
        )
    except (TimetableEntry.DoesNotExist, ValueError, TypeError):
        return None


def list_active_entries_for_branch(branch_id):
    return TimetableEntry.objects.filter(
        timetable__batch__course__department__branch_id=branch_id,
        status=TimetableEntryStatus.ACTIVE,
        is_active=True,
    ).select_related("timetable", "batch_subject", "period_slot", "faculty", "room")


def list_faculty_teaching_slots(branch_id, faculty_id):
    """Active timetable entries taught by a faculty member, for upload pickers."""
    return (
        TimetableEntry.objects.filter(
            timetable__batch__course__department__branch_id=branch_id,
            faculty_id=faculty_id,
            status=TimetableEntryStatus.ACTIVE,
            is_active=True,
        )
        .select_related(
            "timetable__batch", "batch_subject__subject", "period_slot",
        )
        .order_by("day_of_week", "period_slot__sequence")
    )


def find_clashing_entries(
    branch_id,
    *,
    day_of_week,
    period_slot_id,
    faculty_id=None,
    room_id=None,
    exclude_entry_id=None,
):
    base = TimetableEntry.objects.filter(
        timetable__batch__course__department__branch_id=branch_id,
        day_of_week=day_of_week,
        period_slot_id=period_slot_id,
        status=TimetableEntryStatus.ACTIVE,
        is_active=True,
    )
    if exclude_entry_id:
        base = base.exclude(pk=exclude_entry_id)

    clashes = []
    if faculty_id:
        faculty_hits = base.filter(faculty_id=faculty_id)
        if faculty_hits.exists():
            clashes.append(("faculty", faculty_hits))
    if room_id:
        room_hits = base.filter(room_id=room_id)
        if room_hits.exists():
            clashes.append(("room", room_hits))
    return clashes


def create_timetable_entry(
    *,
    timetable,
    batch_subject,
    period_slot,
    day_of_week,
    faculty_id=None,
    room_id=None,
    status=TimetableEntryStatus.ACTIVE,
    user=None,
) -> TimetableEntry:
    return TimetableEntry.objects.create(
        timetable=timetable,
        batch_subject=batch_subject,
        period_slot=period_slot,
        day_of_week=day_of_week,
        faculty_id=faculty_id,
        room_id=room_id,
        status=status,
        created_by=user,
        updated_by=user,
    )


def update_timetable_entry(entry: TimetableEntry, fields: dict, user=None) -> TimetableEntry:
    for k, v in fields.items():
        setattr(entry, k, v)
    if fields:
        entry.version += 1
        if user:
            entry.updated_by = user
        entry.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return entry


def soft_delete_timetable_entry(entry: TimetableEntry, user=None) -> TimetableEntry:
    entry.soft_delete(user)
    entry.version += 1
    entry.save(update_fields=["version", "updated_at"])
    return entry


def soft_delete_timetable_entries_for_branch_year(branch_id, academic_year_id, user=None):
    TimetableEntry.objects.filter(
        timetable__batch__academic_year_id=academic_year_id,
        timetable__batch__course__department__branch_id=branch_id,
        is_active=True,
    ).update(is_active=False)
