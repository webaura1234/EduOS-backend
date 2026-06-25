"""Interactors — exam seating generation."""

import random
import secrets
from collections import defaultdict

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.academics.queries import timetable as tt_q
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import registration as reg_q
from apps.examinations.queries import seating as seat_q


def _seat_capacity(room, slot) -> int:
    if slot and slot.max_capacity and room.pk == slot.room_id:
        return slot.max_capacity
    return room.capacity


def _build_seating_plan(slot, allocations, total_students, note: str, *, generated_at=None) -> dict:
    return {
        "examSlotId": str(slot.pk),
        "generatedAt": generated_at or timezone.now().isoformat(),
        "totalStudents": total_students,
        "allocations": allocations,
        "note": note,
    }


def shuffle_students(students, *, order: str = "random", seed: int | None = None) -> list:
    ordered = list(students)
    if order == "alphabetical":
        return sorted(ordered, key=lambda r: r.student.user.full_name.lower())
    rng = random.Random(seed) if seed is not None else secrets.SystemRandom()
    rng.shuffle(ordered)
    return ordered


def _allocate_students_to_rooms(
    *, slot, rooms, students, seating_order: str = "random", seed: int | None = None
) -> tuple[list[dict], int]:
    ordered_students = shuffle_students(students, order=seating_order, seed=seed)
    idx = 0
    allocations = []

    for room in rooms:
        if idx >= len(ordered_students):
            break
        capacity = _seat_capacity(room, slot) if slot else room.capacity
        take = min(capacity, len(ordered_students) - idx)
        seats = []
        for seat_no in range(1, take + 1):
            reg = ordered_students[idx + seat_no - 1]
            seats.append(
                {
                    "studentId": str(reg.student.student_profile_id),
                    "enrollmentId": str(reg.student_id),
                    "studentName": reg.student.user.full_name,
                    "seatNo": seat_no,
                }
            )
        allocations.append(
            {
                "roomId": str(room.pk),
                "roomName": room.name,
                "seats": seats,
            }
        )
        idx += take

    return allocations, len(ordered_students) - idx


def build_plan_from_db(slot) -> dict | None:
    seatings = list(seat_q.list_seatings_for_slot(slot.pk))
    if not seatings:
        return None

    by_room: dict[str, dict] = {}
    for seating in seatings:
        room_id = str(seating.room_id)
        if room_id not in by_room:
            by_room[room_id] = {
                "roomId": room_id,
                "roomName": seating.room.name,
                "seats": [],
            }
        by_room[room_id]["seats"].append(
            {
                "studentId": str(seating.student.student_profile_id),
                "enrollmentId": str(seating.student_id),
                "studentName": seating.student.user.full_name,
                "seatNo": int(seating.seat_number) if str(seating.seat_number).isdigit() else seating.seat_number,
            }
        )

    allocations = list(by_room.values())
    for allocation in allocations:
        allocation["seats"].sort(key=lambda s: int(s["seatNo"]) if str(s["seatNo"]).isdigit() else str(s["seatNo"]))

    generated_at = max(s.created_at for s in seatings).isoformat()
    return _build_seating_plan(
        slot,
        allocations,
        len(seatings),
        "Loaded from saved seating.",
        generated_at=generated_at,
    )


def list_plans_for_exam(exam_id) -> list[dict]:
    plans = []
    for slot in exam_q.list_schedule_slots(exam_id):
        plan = build_plan_from_db(slot)
        if plan:
            plans.append(plan)
    return plans


def preflight_seating(exam, *, branch_id, slot_ids=None) -> dict:
    slots = list(exam_q.list_schedule_slots(exam.pk))
    if slot_ids:
        slot_id_set = {str(sid) for sid in slot_ids}
        slots = [s for s in slots if str(s.pk) in slot_id_set]

    items = []
    ready = 0
    for slot in slots:
        registrations = list(reg_q.list_registrations(exam.pk, batch_id=slot.batch_id))
        room = tt_q.get_room(branch_id, slot.room_id)
        capacity = _seat_capacity(room, slot) if room else 0
        reg_count = len(registrations)

        issues = []
        status = "ready"
        if not room:
            issues.append("Room not found.")
            status = "blocked"
        if reg_count == 0:
            issues.append("No registered students.")
            status = "blocked"
        elif room and reg_count > capacity:
            issues.append(f"Room capacity {capacity} is less than {reg_count} students.")
            status = "warning"

        if status == "ready":
            ready += 1

        items.append(
            {
                "examSlotId": str(slot.pk),
                "classLabel": slot.batch.name,
                "subjectName": slot.subject.name,
                "registeredCount": reg_count,
                "roomCapacity": capacity,
                "status": status,
                "issues": issues,
            }
        )

    return {
        "totalSlots": len(items),
        "readyCount": ready,
        "items": items,
    }


def _persist_allocations(*, slot, allocations, user=None) -> None:
    seat_q.soft_delete_seatings_for_slot(slot.pk, user=user)
    rows = []
    for allocation in allocations:
        room_id = allocation["roomId"]
        for seat in allocation["seats"]:
            rows.append(
                {
                    "schedule_slot_id": slot.pk,
                    "student_id": seat["enrollmentId"],
                    "room_id": room_id,
                    "seat_number": str(seat["seatNo"]),
                }
            )
    if rows:
        seat_q.bulk_create_seatings(rows, user=user)


def _note_for_allocation(*, remaining, rooms, allocations) -> str:
    if remaining > 0:
        return f"Not enough seats: {remaining} students unallocated. Add more rooms or increase capacity."
    if len(rooms) > 1 and allocations and len(allocations[-1]["seats"]) < rooms[-1].capacity:
        return "Auto-generated; last room partially filled (EC-EXAM-05)."
    return "Auto-generated with random seating."


@transaction.atomic
def generate_seating_for_slot(
    exam,
    slot,
    *,
    branch_id,
    room_ids=None,
    seating_order: str = "random",
    seed: int | None = None,
    user=None,
) -> dict:
    """Generate seating for one schedule slot (EC-EXAM-05 partial last room)."""
    if slot.exam_id != exam.pk:
        raise ValidationError({"examSlotId": "Schedule slot does not belong to this exam."})

    rooms = []
    if room_ids:
        for room_id in room_ids:
            room = tt_q.get_room(branch_id, room_id)
            if not room:
                raise ValidationError({"roomIds": f"Room {room_id} not found in this branch."})
            rooms.append(room)
    else:
        room = tt_q.get_room(branch_id, slot.room_id)
        if not room:
            raise ValidationError({"roomId": "Schedule slot room not found."})
        rooms = [room]

    registrations = list(reg_q.list_registrations(exam.pk, batch_id=slot.batch_id))
    if not registrations:
        raise ValidationError({"classSectionId": "No registered students for this batch."})

    allocations, remaining = _allocate_students_to_rooms(
        slot=slot, rooms=rooms, students=registrations, seating_order=seating_order, seed=seed
    )
    _persist_allocations(slot=slot, allocations=allocations, user=user)

    note = _note_for_allocation(remaining=remaining, rooms=rooms, allocations=allocations)
    if seating_order == "alphabetical":
        note = note.replace("random", "alphabetical")

    return _build_seating_plan(slot, allocations, len(registrations), note)


@transaction.atomic
def generate_seating_bulk(
    exam,
    *,
    branch_id,
    slot_ids=None,
    seating_order: str = "random",
    seed: int | None = None,
    user=None,
) -> dict:
    slots = list(exam_q.list_schedule_slots(exam.pk))
    if slot_ids:
        slot_id_set = {str(sid) for sid in slot_ids}
        slots = [s for s in slots if str(s.pk) in slot_id_set]
    if not slots:
        raise ValidationError({"examId": "No schedule slots to generate seating for."})

    plans = []
    errors = []
    for slot in slots:
        try:
            plans.append(
                generate_seating_for_slot(
                    exam,
                    slot,
                    branch_id=branch_id,
                    seating_order=seating_order,
                    seed=seed,
                    user=user,
                )
            )
        except ValidationError as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"error": str(exc.detail)}
            errors.append({"examSlotId": str(slot.pk), "errors": detail})
        except Exception as exc:
            errors.append({"examSlotId": str(slot.pk), "errors": {"error": str(exc)}})

    return {"seatingPlans": plans, "errors": errors}


@transaction.atomic
def generate_combined_hall(
    exam,
    *,
    branch_id,
    slot_ids,
    room_ids,
    seating_order: str = "random",
    seed: int | None = None,
    user=None,
) -> dict:
    if not slot_ids:
        raise ValidationError({"examSlotIds": "At least one slot is required for combined hall seating."})
    if not room_ids:
        raise ValidationError({"roomIds": "At least one hall room is required."})

    slots = []
    for slot_id in slot_ids:
        slot = exam_q.get_schedule_slot(exam.pk, slot_id)
        if not slot:
            raise ValidationError({"examSlotIds": f"Schedule slot {slot_id} not found for this exam."})
        slots.append(slot)

    windows = {(s.start_at, s.end_at) for s in slots}
    if len(windows) > 1:
        raise ValidationError(
            {"examSlotIds": "Combined hall requires all selected slots to share the same date and time."}
        )

    rooms = []
    for room_id in room_ids:
        room = tt_q.get_room(branch_id, room_id)
        if not room:
            raise ValidationError({"roomIds": f"Room {room_id} not found in this branch."})
        rooms.append(room)

    registrations = []
    slot_by_enrollment = {}
    seen_enrollments = set()
    for slot in slots:
        for reg in reg_q.list_registrations(exam.pk, batch_id=slot.batch_id):
            if reg.student_id in seen_enrollments:
                continue
            seen_enrollments.add(reg.student_id)
            registrations.append(reg)
            slot_by_enrollment[reg.student_id] = slot

    if not registrations:
        raise ValidationError({"examSlotIds": "No registered students across selected slots."})

    ordered = shuffle_students(registrations, order=seating_order, seed=seed)
    idx = 0
    hall_allocations: list[dict] = []
    seat_assignments: list[tuple] = []

    for room in rooms:
        if idx >= len(ordered):
            break
        capacity = room.capacity
        take = min(capacity, len(ordered) - idx)
        seats = []
        for seat_no in range(1, take + 1):
            reg = ordered[idx + seat_no - 1]
            seats.append(
                {
                    "studentId": str(reg.student.student_profile_id),
                    "enrollmentId": str(reg.student_id),
                    "studentName": reg.student.user.full_name,
                    "seatNo": seat_no,
                    "classLabel": slot_by_enrollment[reg.student_id].batch.name,
                }
            )
            seat_assignments.append((slot_by_enrollment[reg.student_id], reg, room, seat_no))
        hall_allocations.append({"roomId": str(room.pk), "roomName": room.name, "seats": seats})
        idx += take

    remaining = len(ordered) - idx
    for slot in slots:
        seat_q.soft_delete_seatings_for_slot(slot.pk, user=user)

    rows_by_slot: dict = defaultdict(list)
    for slot, reg, room, seat_no in seat_assignments:
        rows_by_slot[slot.pk].append(
            {
                "schedule_slot_id": slot.pk,
                "student_id": reg.student_id,
                "room_id": room.pk,
                "seat_number": str(seat_no),
            }
        )

    plans = []
    for slot in slots:
        slot_rows = rows_by_slot.get(slot.pk, [])
        if slot_rows:
            seat_q.bulk_create_seatings(slot_rows, user=user)
        slot_allocations = [
            {
                "roomId": str(room.pk),
                "roomName": room.name,
                "seats": [
                    {
                        "studentId": str(reg.student.student_profile_id),
                        "enrollmentId": str(reg.student_id),
                        "studentName": reg.student.user.full_name,
                        "seatNo": seat_no,
                    }
                    for s, reg, r, seat_no in seat_assignments
                    if s.pk == slot.pk and r.pk == room.pk
                ],
            }
            for room in rooms
        ]
        slot_allocations = [a for a in slot_allocations if a["seats"]]
        reg_count = len(slot_rows)
        if reg_count:
            note = (
                f"Combined hall seating ({len(slots)} classes)."
                if remaining == 0
                else f"Combined hall; {remaining} students unallocated across hall."
            )
            plans.append(_build_seating_plan(slot, slot_allocations, reg_count, note))

    return {
        "seatingPlans": plans,
        "hallAllocations": hall_allocations,
        "errors": [],
        "unallocated": remaining,
    }


@transaction.atomic
def generate_seating_for_exam(
    exam,
    *,
    branch_id,
    exam_slot_id=None,
    exam_slot_ids=None,
    room_ids=None,
    mode: str = "per_slot",
    seating_order: str = "random",
    seed: int | None = None,
    user=None,
) -> dict:
    if mode == "combined":
        return generate_combined_hall(
            exam,
            branch_id=branch_id,
            slot_ids=exam_slot_ids or ([exam_slot_id] if exam_slot_id else []),
            room_ids=room_ids or [],
            seating_order=seating_order,
            seed=seed,
            user=user,
        )

    if exam_slot_ids:
        return generate_seating_bulk(
            exam,
            branch_id=branch_id,
            slot_ids=exam_slot_ids,
            seating_order=seating_order,
            seed=seed,
            user=user,
        )

    if exam_slot_id:
        slot = exam_q.get_schedule_slot(exam.pk, exam_slot_id)
        if not slot:
            raise ValidationError({"examSlotId": "Schedule slot not found for this exam."})
        plan = generate_seating_for_slot(
            exam,
            slot,
            branch_id=branch_id,
            room_ids=room_ids,
            seating_order=seating_order,
            seed=seed,
            user=user,
        )
        return {"seatingPlans": [plan], "errors": []}

    return generate_seating_bulk(
        exam,
        branch_id=branch_id,
        slot_ids=None,
        seating_order=seating_order,
        seed=seed,
        user=user,
    )
