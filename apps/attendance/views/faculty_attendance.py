"""Faculty attendance — today's classes for the logged-in faculty + existing records.

Read aggregate in the FacultyAttendanceData shape. Marking a session's roster uses the
existing session open/mark endpoints; single-record correction uses CorrectRecordView.
"""

import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.attendance.interactors import marking as mark_i
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.attendance.queries import record as record_q
from apps.attendance.queries import roster as roster_q
from apps.attendance.views.overview import _record


def _ensure_roster_records(branch, entry, user):
    """Open-or-get the session for a class and create 'absent' placeholders for any
    roster student without a record yet. Never overwrites an existing mark."""
    session = mark_i.open_session(
        branch=branch, date=datetime.date.today(),
        batch_subject_id=entry.batch_subject_id,
        period_slot_id=entry.period_slot_id,
        batch_id=entry.timetable.batch_id, faculty_id=user.pk, user=user,
    )
    existing = {r.student_id for r in record_q.list_records_for_session(session.pk)}
    now = timezone.now()
    for enrollment in roster_q.students_in_batch(entry.timetable.batch_id):
        if enrollment.pk not in existing:
            record_q.upsert_record(
                session=session, student=enrollment, status="absent",
                marked_at=now, marked_by=None, user=user,
            )
    return session


class FacultyAttendanceView(APIView):
    """GET → FacultyAttendanceData for the logged-in faculty's classes today."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    @transaction.atomic
    def get(self, request) -> Response:
        branch = resolve_branch(request)
        today = datetime.date.today()
        weekday = today.isoweekday()

        sessions, records = [], []
        for e in tt_q.list_active_entries_for_branch(branch.pk):
            if (e.faculty_id != request.user.pk or e.day_of_week != weekday
                    or not e.batch_subject_id):
                continue
            subject = e.batch_subject.subject
            # Ensure the session + roster placeholder records exist so the faculty
            # has a full class to mark (absent until they mark present).
            sess = _ensure_roster_records(branch, e, request.user)
            record_ids = []
            for r in record_q.list_records_for_session(sess.pk):
                records.append(_record(r))
                record_ids.append(str(r.id))
            sessions.append({
                "date": today.isoformat(),
                "classSectionId": str(e.timetable.batch_id),
                "classLabel": e.timetable.batch.name,
                "subjectId": str(subject.id),
                "subjectName": subject.name,
                "recordIds": record_ids,
            })

        blocked = roster_q.is_student_holiday(branch.pk, today)
        geo_enabled = branch.geofence_radius_m is not None and branch.latitude is not None

        return Response({
            "date": today.isoformat(),
            "sessions": sessions,
            "records": records,
            "holiday": {"blocked": blocked, "date": today.isoformat()},
            "geoFence": {
                "enabled": bool(geo_enabled),
                "campusLabel": branch.name,
                "latitude": float(branch.latitude) if branch.latitude is not None else 0,
                "longitude": float(branch.longitude) if branch.longitude is not None else 0,
                "radiusMeters": branch.geofence_radius_m or 0,
            },
        })
