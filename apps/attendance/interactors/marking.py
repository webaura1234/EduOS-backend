"""Interactors — open session + mark attendance, enforcing all attendance edge cases.

EC-ATT-01 holiday block · EC-ATT-02 late mark · EC-ATT-03 geo flag (backend-validated) ·
EC-ATT-06 idempotent sync · frozen-year guard · day-wise vs session-wise modes.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import timetable as tt_q
from apps.attendance.enums import AttendanceStatus, AuditType, SessionStatus
from apps.attendance.helpers import is_late_mark, is_outside_geofence
from apps.attendance.queries import audit as audit_q
from apps.attendance.queries import leave as leave_q
from apps.attendance.queries import record as record_q
from apps.attendance.queries import roster as roster_q
from apps.attendance.queries import session as session_q
from apps.organizations.enums import AttendanceMode


@transaction.atomic
def open_session(*, branch, date, batch_subject_id=None, period_slot_id=None,
                 batch_id=None, faculty_id=None, is_exam_day=False, user=None):
    """
    Create or return the session for a class on a date.

    The shape depends on the tenant's attendance_mode:
      - day mode:     requires batchId (one session per batch per day)
      - session mode: requires batchSubjectId + periodSlotId
    """
    mode = roster_q.attendance_mode(branch)
    fac = faculty_id or (user.pk if user and user.role == "faculty" else None)

    if mode == AttendanceMode.DAY:
        if not batch_id:
            raise ValidationError({"batchId": "batchId is required in day-wise attendance mode."})
        batch = struct_q.get_batch(branch.pk, batch_id)
        if not batch:
            raise ValidationError({"batchId": "Batch not found in this branch."})
        if batch.academic_year.is_frozen:
            raise ValidationError("Cannot modify attendance in a frozen academic year.")
        existing = session_q.get_day_session(batch_id=batch.pk, date=date)
        if existing:
            return existing
        return session_q.create_session(
            branch_id=branch.pk, batch=batch, mode=mode, date=date,
            faculty_id=fac, is_exam_day=is_exam_day, status=SessionStatus.IN_PROGRESS, user=user,
        )

    # session mode
    if not (batch_subject_id and period_slot_id):
        raise ValidationError("batchSubjectId and periodSlotId are required in session-wise mode.")
    bs = curr_q.get_batch_subject(branch.pk, batch_subject_id)
    if not bs:
        raise ValidationError({"batchSubjectId": "Batch subject not found in this branch."})
    if bs.batch.academic_year.is_frozen:
        raise ValidationError("Cannot modify attendance in a frozen academic year.")
    slot = tt_q.get_period_slot(branch.pk, period_slot_id)
    if not slot:
        raise ValidationError({"periodSlotId": "Period slot not found."})
    existing = session_q.get_session_by_natural_key(
        batch_subject_id=bs.pk, date=date, period_slot_id=slot.pk
    )
    if existing:
        return existing
    return session_q.create_session(
        branch_id=branch.pk, batch=bs.batch, mode=mode, batch_subject=bs, period_slot=slot,
        date=date, faculty_id=fac, is_exam_day=is_exam_day, status=SessionStatus.IN_PROGRESS, user=user,
    )


@transaction.atomic
def mark_session(*, branch, session, marks: list[dict], user=None):
    """
    Bulk-mark a session. Each mark: {studentId, status, geoLat?, geoLng?, geoValid?}.

    Idempotent (EC-ATT-06). Works the same in day and session mode (the session
    already carries its batch).
    """
    if session.batch.academic_year.is_frozen:
        raise ValidationError("Cannot modify attendance in a frozen academic year.")

    # EC-ATT-01: no marking on a student holiday.
    if roster_q.is_student_holiday(branch.pk, session.date):
        raise ValidationError("Cannot mark attendance on an institution holiday.")

    now = timezone.now()
    slot_end = session.period_slot.end_time if session.period_slot_id else None
    results = []

    for item in marks:
        student = roster_q.get_student_profile_in_branch(branch.pk, item["studentId"])
        if not student:
            raise ValidationError({"studentId": f"Student {item['studentId']} not found in this branch."})
        if student.current_batch_id != session.batch_id:
            raise ValidationError({"studentId": f"Student {item['studentId']} is not in this class."})

        requested = item.get("status", AttendanceStatus.PRESENT)
        geo_lat = item.get("geoLat")
        geo_lng = item.get("geoLng")
        # EC-ATT-03: backend geo-fence validation against the branch location.
        geo_failed = (item.get("geoValid") is False) or is_outside_geofence(branch, geo_lat, geo_lng)

        if geo_failed:
            status = AttendanceStatus.FLAGGED
        elif leave_q.has_approved_leave(student.pk, session.date):
            status = AttendanceStatus.LEAVE
        else:
            status = requested

        # EC-ATT-02 / F-108: late mark (only meaningful in session mode with a slot).
        late = bool(slot_end) and is_late_mark(session.date, slot_end, now)

        record, _ = record_q.upsert_record(
            session=session, student=student, status=status, marked_at=now,
            marked_by=user, geo_lat=geo_lat, geo_lng=geo_lng, late_mark=late, user=user,
        )

        if geo_failed:
            audit_q.create_audit(
                record=record, audit_type=AuditType.GEO_FENCE_FAILURE, actor=user,
                new_status=status, reason="Geo-fence validation failed.",
                metadata={"geoLat": str(geo_lat), "geoLng": str(geo_lng)},
            )
        if late:
            audit_q.create_audit(
                record=record, audit_type=AuditType.LATE_MARKING, actor=user,
                new_status=status, reason="Marked more than 2 hours after class end.",
                metadata={"markedAt": now.isoformat()},
            )
        results.append(record)

    session_q.update_session(session, {"status": SessionStatus.COMPLETED}, user=user)
    return results
