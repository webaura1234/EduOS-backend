"""Queries — exam seating sessions."""

from apps.examinations.models import ExamSeatingSession


def create_seating_session(*, exam_id, name, hall_room_id, start_at, end_at, user=None) -> ExamSeatingSession:
    return ExamSeatingSession.objects.create(
        exam_id=exam_id,
        name=name,
        hall_room_id=hall_room_id,
        start_at=start_at,
        end_at=end_at,
        created_by=user,
        updated_by=user,
    )


def get_seating_session(exam_id, session_id) -> ExamSeatingSession | None:
    return (
        ExamSeatingSession.objects.filter(exam_id=exam_id, pk=session_id, is_active=True)
        .select_related("hall_room")
        .first()
    )


def list_seating_sessions(exam_id):
    return (
        ExamSeatingSession.objects.filter(exam_id=exam_id, is_active=True)
        .select_related("hall_room")
        .order_by("start_at")
    )
