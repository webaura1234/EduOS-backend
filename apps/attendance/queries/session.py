"""Queries — AttendanceSession (all ORM for sessions)."""

from apps.attendance.models import AttendanceSession


def get_session(branch_id, session_id) -> AttendanceSession | None:
    try:
        return AttendanceSession.objects.select_related(
            "batch", "batch__academic_year", "batch_subject", "batch_subject__subject", "period_slot"
        ).get(branch_id=branch_id, pk=session_id, is_active=True)
    except (AttendanceSession.DoesNotExist, ValueError, TypeError):
        return None


def get_session_by_natural_key(*, batch_subject_id, date, period_slot_id) -> AttendanceSession | None:
    try:
        return AttendanceSession.objects.get(
            batch_subject_id=batch_subject_id, date=date, period_slot_id=period_slot_id, is_active=True
        )
    except AttendanceSession.DoesNotExist:
        return None


def get_day_session(*, batch_id, date) -> AttendanceSession | None:
    try:
        return AttendanceSession.objects.select_related("batch", "batch__academic_year").get(
            batch_id=batch_id, date=date, batch_subject__isnull=True, is_active=True
        )
    except AttendanceSession.DoesNotExist:
        return None


def create_session(*, branch_id, batch, mode, date, batch_subject=None, period_slot=None,
                   faculty_id=None, is_exam_day=False, status="scheduled", user=None) -> AttendanceSession:
    return AttendanceSession.objects.create(
        branch_id=branch_id, batch=batch, mode=mode, batch_subject=batch_subject,
        period_slot=period_slot, date=date, faculty_id=faculty_id, is_exam_day=is_exam_day,
        status=status, created_by=user, updated_by=user,
    )


def update_session(session: AttendanceSession, fields: dict, user=None) -> AttendanceSession:
    for k, v in fields.items():
        setattr(session, k, v)
    if fields:
        session.version += 1
        if user:
            session.updated_by = user
        session.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return session


def list_sessions_for_date(branch_id, date):
    return (
        AttendanceSession.objects.filter(branch_id=branch_id, date=date, is_active=True)
        .select_related("batch", "batch_subject", "batch_subject__subject", "period_slot", "faculty")
        .order_by("period_slot__sequence")
    )
