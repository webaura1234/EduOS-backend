"""Interactors — combined hall seating sessions."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.academics.queries import timetable as tt_q
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import seating_session as session_q


@transaction.atomic
def create_seating_session(
    exam,
    *,
    branch_id,
    name,
    hall_room_id,
    slot_ids,
    user=None,
) -> dict:
    if not slot_ids:
        raise ValidationError({"examSlotIds": "At least one slot is required."})

    hall_room = tt_q.get_room(branch_id, hall_room_id)
    if not hall_room:
        raise ValidationError({"hallRoomId": "Hall room not found in this branch."})

    slots = []
    for slot_id in slot_ids:
        slot = exam_q.get_schedule_slot(exam.pk, slot_id)
        if not slot:
            raise ValidationError({"examSlotIds": f"Slot {slot_id} not found."})
        slots.append(slot)

    windows = {(s.start_at, s.end_at) for s in slots}
    if len(windows) > 1:
        raise ValidationError(
            {"examSlotIds": "All slots must share the same date and time for a combined hall session."}
        )

    start_at, end_at = next(iter(windows))
    session = session_q.create_seating_session(
        exam_id=exam.pk,
        name=name.strip() or f"Hall session — {hall_room.name}",
        hall_room_id=hall_room_id,
        start_at=start_at,
        end_at=end_at,
        user=user,
    )

    for slot in slots:
        exam_q.update_schedule_slot(
            slot,
            {"seating_session_id": session.pk, "room_id": hall_room_id},
            user=user,
        )

    return {
        "session": {
            "id": str(session.pk),
            "name": session.name,
            "hallRoomId": str(session.hall_room_id),
            "hallRoomName": hall_room.name,
            "startAt": session.start_at.isoformat(),
            "endAt": session.end_at.isoformat(),
            "examSlotIds": [str(s.pk) for s in slots],
        }
    }
