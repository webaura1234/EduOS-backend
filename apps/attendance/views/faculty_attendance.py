"""Faculty attendance — today's classes for the logged-in faculty + existing records.

Read aggregate in the FacultyAttendanceData shape. Marking a session's roster uses the
existing session open/mark endpoints; single-record correction uses CorrectRecordView.
"""

import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import Batch
from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.attendance.helpers import open_session_with_roster
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.attendance.queries import record as record_q
from apps.attendance.queries import roster as roster_q
from apps.attendance.queries import session as session_q
from apps.attendance.views.overview import _record


def _ensure_roster_records(branch, entry, user):
    """Session-mode: open-or-get the period session for a timetable entry + placeholders."""
    return open_session_with_roster(
        branch=branch,
        date=datetime.date.today(),
        batch_subject_id=entry.batch_subject_id,
        period_slot_id=entry.period_slot_id,
        batch_id=entry.timetable.batch_id,
        faculty_id=user.pk,
        user=user,
    )


def _ensure_day_roster(branch, batch, user):
    """Day-mode: open-or-get the single day session for a batch + placeholders."""
    return open_session_with_roster(
        branch=branch,
        date=datetime.date.today(),
        batch_id=batch.pk,
        faculty_id=user.pk,
        user=user,
    )


def _class_teacher_batches(branch_id, faculty_id):
    """Batches where this faculty is the class teacher (day-wise rosters they own)."""
    return (
        Batch.objects.filter(
            course__department__branch_id=branch_id,
            class_teacher_id=faculty_id, is_active=True,
        )
        .select_related("course")
        .order_by("course__name", "name")
    )


class FacultyAttendanceView(APIView):
    """GET → FacultyAttendanceData for the logged-in faculty's classes today."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    @transaction.atomic
    def get(self, request) -> Response:
        branch = resolve_branch(request)
        today = datetime.date.today()
        weekday = today.isoweekday()

        sessions, records = [], []
        mode = roster_q.attendance_mode(branch)

        def _emit(sess, batch_id, class_label, subject_id, subject_name):
            record_ids = []
            for r in record_q.list_records_for_session(sess.pk):
                records.append(_record(r))
                record_ids.append(str(r.id))
            sessions.append({
                "date": today.isoformat(),
                "classSectionId": str(batch_id),
                "classLabel": class_label,
                "subjectId": subject_id,
                "subjectName": subject_name,
                "recordIds": record_ids,
            })

        if mode == "day":
            # Day-wise: one whole-day session per class the faculty is class teacher of.
            for batch in _class_teacher_batches(branch.pk, request.user.pk):
                sess = _ensure_day_roster(branch, batch, request.user)
                label = (f"{batch.course.name} - {batch.name}"
                         if batch.course_id else batch.name)
                _emit(sess, batch.pk, label, "", "Day attendance")
        else:
            # Session-wise: one session per timetable period the faculty teaches today.
            for e in tt_q.list_active_entries_for_branch(branch.pk):
                if (e.faculty_id != request.user.pk or e.day_of_week != weekday
                        or not e.batch_subject_id):
                    continue
                subject = e.batch_subject.subject
                sess = _ensure_roster_records(branch, e, request.user)
                _emit(sess, e.timetable.batch_id, e.timetable.batch.name,
                      str(subject.id), subject.name)

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


_VALID_STATUSES = {"present", "absent", "late", "excused", "leave"}


class FacultyMarkRecordView(APIView):
    """PATCH a single roster record's status. The class teacher (or the session's faculty)
    may mark their own class; admins may mark any. Mirrors the admin correct flow but is
    scoped to the faculty who owns the class."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def patch(self, request, record_id) -> Response:
        branch = resolve_branch(request)
        record = record_q.get_record(branch.pk, record_id)
        if not record:
            return Response({"error": "Not found."}, status=http.HTTP_404_NOT_FOUND)

        # Authorization: only the class teacher of the session's batch or the session's
        # own faculty may mark it; admins/super-admins bypass.
        if request.user.role not in ("admin", "super_admin"):
            session = record.session
            owns = (
                (session.batch_id and session.batch.class_teacher_id == request.user.pk)
                or session.faculty_id == request.user.pk
            )
            if not owns:
                return Response(
                    {"error": "You can only mark attendance for your own class."},
                    status=http.HTTP_403_FORBIDDEN,
                )

        new_status = request.data.get("newStatus")
        if new_status not in _VALID_STATUSES:
            return Response({"error": "Invalid status."}, status=http.HTTP_400_BAD_REQUEST)

        record, _ = record_q.upsert_record(
            session=record.session, student=record.student, status=new_status,
            marked_at=timezone.now(), marked_by=request.user, user=request.user,
        )
        return Response({"record": _record(record)})


class FacultyLiveAttendanceView(APIView):
    """GET → LiveAttendanceSnapshot: today's attendance per class the faculty is
    class teacher of (class name + present/total). Scoped to her own classes."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        today = datetime.date.today()

        batches = list(_class_teacher_batches(branch.pk, request.user.pk))
        batch_ids = [b.pk for b in batches]
        # Three bulk queries instead of 3 per batch.
        roster_counts = roster_q.roster_counts_for_batches(batch_ids)
        session_by_batch = session_q.day_session_ids_for_batches(batch_ids, today)
        counts_by_session = record_q.status_counts_for_sessions(list(session_by_batch.values()))

        classes = []
        total_present = total_all = 0
        for batch in batches:
            bid = str(batch.pk)
            roster = roster_counts.get(bid, 0)
            present = 0
            sid = session_by_batch.get(bid)
            if sid:
                c = counts_by_session.get(sid, {})
                present = c.get("present", 0) + c.get("late", 0)
            label = (f"{batch.course.name} - {batch.name}" if batch.course_id else batch.name)
            classes.append({
                "classId": bid,
                "classLabel": label,
                "present": present,
                "total": roster,
            })
            total_present += present
            total_all += roster

        percent = round(total_present / total_all * 100) if total_all else 0
        return Response({
            "present": total_present,
            "total": total_all,
            "percent": percent,
            "classes": classes,
            "updatedAt": timezone.now().isoformat(),
        })


class FacultyBulkMarkView(APIView):
    """PATCH { records: [{recordId, status}] } — save a whole class's attendance at once.

    Class-teacher (or the session's faculty) only; admins bypass. Built for large
    rosters: one request marks every student."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    @transaction.atomic
    def patch(self, request) -> Response:
        branch = resolve_branch(request)
        rows = request.data.get("records") or []
        if not isinstance(rows, list):
            return Response({"error": "records must be a list."}, status=http.HTTP_400_BAD_REQUEST)

        is_admin = request.user.role in ("admin", "super_admin")
        now = timezone.now()
        updated = 0
        for row in rows:
            rid = row.get("recordId")
            status = row.get("status")
            if status not in _VALID_STATUSES:
                continue
            rec = record_q.get_record(branch.pk, rid)
            if not rec:
                continue
            if not is_admin:
                session = rec.session
                owns = (
                    (session.batch_id and session.batch.class_teacher_id == request.user.pk)
                    or session.faculty_id == request.user.pk
                )
                if not owns:
                    continue
            record_q.upsert_record(
                session=rec.session, student=rec.student, status=status,
                marked_at=now, marked_by=request.user, user=request.user,
            )
            updated += 1
        return Response({"updated": updated})
