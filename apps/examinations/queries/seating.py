"""Queries — exam seating allocation (all ORM here)."""

from apps.examinations.models import Seating


def list_seatings_for_slot(schedule_slot_id):
    return (
        Seating.objects.filter(schedule_slot_id=schedule_slot_id, is_active=True)
        .select_related("student", "student__student_profile__user", "room")
        .order_by("room_id", "seat_number")
    )


def list_seatings_for_exam(exam_id):
    return (
        Seating.objects.filter(schedule_slot__exam_id=exam_id, is_active=True)
        .select_related("schedule_slot", "student", "student__student_profile__user", "room")
        .order_by("schedule_slot__start_at", "room_id", "seat_number")
    )


def clear_seatings_for_slot(schedule_slot_id):
    """Hard-delete prior seating so unique constraints allow regeneration."""
    return Seating.objects.filter(schedule_slot_id=schedule_slot_id).delete()[0]


def soft_delete_seatings_for_slot(schedule_slot_id, user=None):
    return clear_seatings_for_slot(schedule_slot_id)


def bulk_create_seatings(rows: list[dict], user=None) -> list[Seating]:
    created = []
    for row in rows:
        created.append(
            Seating.objects.create(
                schedule_slot_id=row["schedule_slot_id"],
                student_id=row["student_id"],
                room_id=row["room_id"],
                seat_number=row["seat_number"],
                created_by=user,
                updated_by=user,
            )
        )
    return created
