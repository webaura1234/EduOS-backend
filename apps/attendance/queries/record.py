"""Queries — AttendanceRecord (all ORM for records, incl. idempotent upsert)."""

from django.db.models import Count, Q

from apps.attendance.enums import AttendanceStatus
from apps.attendance.models import AttendanceRecord


def get_record(branch_id, record_id) -> AttendanceRecord | None:
    try:
        return AttendanceRecord.objects.select_related(
            "session", "session__batch_subject__batch__academic_year", "student"
        ).get(session__branch_id=branch_id, pk=record_id, is_active=True)
    except (AttendanceRecord.DoesNotExist, ValueError, TypeError):
        return None


def list_flagged(branch_id):
    """Flagged (geo-fence failed) records awaiting admin review (F-103/EC-ATT-03)."""
    return (
        AttendanceRecord.objects.filter(
            session__branch_id=branch_id, status=AttendanceStatus.FLAGGED, is_active=True
        )
        .select_related("session", "student", "student__student_profile__user")
        .order_by("-marked_at")
    )


def list_records_for_session(session_id):
    return (
        AttendanceRecord.objects.filter(session_id=session_id, is_active=True)
        .select_related("student", "student__student_profile__user")
        .order_by("student__student_profile__user__first_name")
    )


def list_records_for_branch(branch_id, *, limit=200):
    """Most-recent attendance records across a branch (admin overview)."""
    return (
        AttendanceRecord.objects.filter(session__branch_id=branch_id, is_active=True)
        .select_related(
            "session",
            "session__batch",
            "session__batch_subject__subject",
            "session__period_slot",
            "student__student_profile__user",
            "marked_by",
        )
        .order_by("-marked_at")[:limit]
    )


def upsert_record(*, session, student, status, marked_at, marked_by=None,
                  geo_lat=None, geo_lng=None, late_mark=False, user=None) -> tuple[AttendanceRecord, bool]:
    """
    Idempotent mark (EC-ATT-06): unique on (session, student) via idempotency_key.
    Returns (record, created).
    """
    key = f"{session.pk}:{student.pk}"
    record, created = AttendanceRecord.objects.update_or_create(
        idempotency_key=key,
        defaults=dict(
            session=session, student=student, status=status, marked_at=marked_at,
            marked_by=marked_by, geo_lat=geo_lat, geo_lng=geo_lng, late_mark=late_mark,
            updated_by=user, is_active=True,
        ),
    )
    if created:
        record.created_by = user
        record.save(update_fields=["created_by"])
    return record, created


def set_absent_records_to_leave(student_id, date_from, date_to, user=None) -> int:
    """When leave is approved, convert already-marked absences in the range to leave."""
    return AttendanceRecord.objects.filter(
        student_id=student_id,
        session__date__gte=date_from,
        session__date__lte=date_to,
        status=AttendanceStatus.ABSENT,
        is_active=True,
    ).update(status=AttendanceStatus.LEAVE, updated_by=user)


def apply_correction(record: AttendanceRecord, new_status, user=None) -> AttendanceRecord:
    record.status = new_status
    record.version += 1
    if user:
        record.updated_by = user
    record.save(update_fields=["status", "version", "updated_by", "updated_at"])
    return record


def status_counts_for_session(session_id) -> dict:
    rows = (
        AttendanceRecord.objects.filter(session_id=session_id, is_active=True)
        .values("status").annotate(n=Count("id"))
    )
    return {r["status"]: r["n"] for r in rows}


def records_for_students_in_range(student_ids, *, date_from, date_to, batch_subject_id=None):
    """All records for a set of students over a date range (for % + reports)."""
    qs = AttendanceRecord.objects.filter(
        student_id__in=student_ids,
        session__date__gte=date_from,
        session__date__lte=date_to,
        is_active=True,
    ).select_related("session", "session__batch_subject", "session__batch_subject__subject")
    if batch_subject_id:
        qs = qs.filter(session__batch_subject_id=batch_subject_id)
    return qs


def aggregate_counts(student_id, *, date_from, date_to, exclude_exam_days, batch_subject_id=None):
    """Return (present_like, excused, total) for one student in a window."""
    qs = AttendanceRecord.objects.filter(
        student_id=student_id,
        session__date__gte=date_from,
        session__date__lte=date_to,
        session__status="completed",
        is_active=True,
    )
    if batch_subject_id:
        qs = qs.filter(session__batch_subject_id=batch_subject_id)
    if exclude_exam_days:
        qs = qs.filter(session__is_exam_day=False)
    agg = qs.aggregate(
        total=Count("id"),
        present_like=Count("id", filter=Q(status__in=[AttendanceStatus.PRESENT, AttendanceStatus.LATE])),
        excused=Count("id", filter=Q(status__in=[AttendanceStatus.EXCUSED, AttendanceStatus.LEAVE])),
    )
    return agg["present_like"] or 0, agg["excused"] or 0, agg["total"] or 0


def aggregate_counts_by_student(student_ids, *, date_from, date_to, exclude_exam_days,
                                batch_subject_id=None) -> dict:
    """Bulk variant of aggregate_counts — ONE grouped query for many students.

    Returns { student_id: (present_like, excused, total) }. Students with no records
    in the window are absent (callers default them to (0, 0, 0)). Same filters as
    aggregate_counts so per-student results are identical.
    """
    qs = AttendanceRecord.objects.filter(
        student_id__in=list(student_ids),
        session__date__gte=date_from,
        session__date__lte=date_to,
        session__status="completed",
        is_active=True,
    )
    if batch_subject_id:
        qs = qs.filter(session__batch_subject_id=batch_subject_id)
    if exclude_exam_days:
        qs = qs.filter(session__is_exam_day=False)
    rows = qs.values("student_id").annotate(
        total=Count("id"),
        present_like=Count("id", filter=Q(status__in=[AttendanceStatus.PRESENT, AttendanceStatus.LATE])),
        excused=Count("id", filter=Q(status__in=[AttendanceStatus.EXCUSED, AttendanceStatus.LEAVE])),
    )
    return {
        r["student_id"]: (r["present_like"], r["excused"], r["total"])
        for r in rows
    }
