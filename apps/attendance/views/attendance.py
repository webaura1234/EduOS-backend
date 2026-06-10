"""Views — sessions, marking, live board, reports, corrections, student/parent summaries."""

import datetime

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin, IsParent, IsStudent
from apps.attendance.interactors import correction as correct_i
from apps.attendance.interactors import marking as mark_i
from apps.attendance.interactors import report as report_i
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.attendance.queries import record as record_q
from apps.attendance.queries import roster as roster_q
from apps.attendance.queries import session as session_q
from apps.attendance.serializers.attendance import (
    AttendanceRecordSerializer,
    AttendanceSessionSerializer,
    CorrectRecordSerializer,
    MarkSessionSerializer,
    OpenSessionSerializer,
    UpdateSessionSerializer,
)


class SessionOpenView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        s = OpenSessionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        session = mark_i.open_session(
            branch=branch, date=d["date"],
            batch_subject_id=d.get("batchSubjectId"), period_slot_id=d.get("periodSlotId"),
            batch_id=d.get("batchId"), faculty_id=d.get("facultyId"),
            is_exam_day=d.get("isExamDay", False), user=request.user,
        )
        return Response({"session": AttendanceSessionSerializer(session).data}, status=http.HTTP_201_CREATED)


class SessionDetailView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def patch(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        session = session_q.get_session(branch.pk, session_id)
        if not session:
            return Response({"error": "Not found."}, status=http.HTTP_404_NOT_FOUND)
        s = UpdateSessionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        session = session_q.update_session(session, {"status": s.validated_data["status"]}, user=request.user)
        return Response({"session": AttendanceSessionSerializer(session).data})


class SessionRosterView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        session = session_q.get_session(branch.pk, session_id)
        if not session:
            return Response({"error": "Not found."}, status=http.HTTP_404_NOT_FOUND)
        existing = {str(r.student_id): r.status for r in record_q.list_records_for_session(session.pk)}
        roster = [
            {"studentId": str(sp.pk), "name": sp.user.full_name, "status": existing.get(str(sp.pk))}
            for sp in roster_q.students_in_batch(session.batch_id)
        ]
        return Response({"session": AttendanceSessionSerializer(session).data, "roster": roster})


class SessionMarkView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def post(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        session = session_q.get_session(branch.pk, session_id)
        if not session:
            return Response({"error": "Session not found."}, status=http.HTTP_404_NOT_FOUND)
        s = MarkSessionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        records = mark_i.mark_session(branch=branch, session=session, marks=s.validated_data["marks"], user=request.user)
        return Response({"records": AttendanceRecordSerializer(records, many=True).data})


class LiveBoardView(APIView):
    """F-101 — today's (or ?date=) attendance status across all classes."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        date_str = request.query_params.get("date")
        date = datetime.date.fromisoformat(date_str) if date_str else datetime.date.today()
        classes = []
        for session in session_q.list_sessions_for_date(branch.pk, date):
            counts = record_q.status_counts_for_session(session.pk)
            classes.append({
                "sessionId": str(session.pk),
                "mode": session.mode,
                "batchId": str(session.batch_id),
                "batchName": session.batch.name,
                "batchSubjectId": str(session.batch_subject_id) if session.batch_subject_id else None,
                "subjectName": session.batch_subject.subject.name if session.batch_subject_id else None,
                "slot": session.period_slot.name if session.period_slot_id else None,
                "status": session.status,
                "counts": counts,
            })
        return Response({"date": date.isoformat(), "classes": classes})


class ShortageReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        threshold = request.query_params.get("threshold")
        return Response(report_i.shortage_report(
            branch, threshold=int(threshold) if threshold else None,
            batch_id=request.query_params.get("batchId"),
        ))


class DetentionReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        return Response(report_i.detention_report(branch, batch_id=request.query_params.get("batchId")))


class MonthlyReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        try:
            year = int(request.query_params["year"])
            month = int(request.query_params["month"])
        except (KeyError, ValueError):
            return Response({"error": "year and month are required integers."}, status=http.HTTP_400_BAD_REQUEST)
        return Response(report_i.monthly_report(
            branch, year=year, month=month, batch_id=request.query_params.get("batchId")
        ))


class CorrectRecordView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, record_id) -> Response:
        branch = resolve_branch(request)
        record = record_q.get_record(branch.pk, record_id)
        if not record:
            return Response({"error": "Not found."}, status=http.HTTP_404_NOT_FOUND)
        s = CorrectRecordSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        record = correct_i.correct_record(
            record=record, new_status=s.validated_data["newStatus"],
            reason=s.validated_data.get("reason", ""), user=request.user,
        )
        return Response({"record": AttendanceRecordSerializer(record).data})


class FlaggedQueueView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        rows = [
            {"recordId": str(r.pk), "studentId": str(r.student_id), "name": r.student.user.full_name,
             "sessionId": str(r.session_id), "markedAt": r.marked_at.isoformat()}
            for r in record_q.list_flagged(branch.pk)
        ]
        return Response({"flagged": rows})


class StudentSummaryView(APIView):
    """F-111 — the logged-in student's own attendance summary."""
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        profile = getattr(request.user, "student_profile", None)
        if not profile:
            return Response({"error": "Student profile not found."}, status=http.HTTP_404_NOT_FOUND)
        return Response(report_i.student_summary(branch, profile))


class ChildSummaryView(APIView):
    """F-112 — a parent views a linked child's attendance summary."""
    permission_classes = [IsAuthenticated, IsParent]

    def get(self, request, student_id) -> Response:
        profile = roster_q.student_for_guardian(request.user.pk, student_id)
        if not profile:
            return Response({"error": "Not a linked child."}, status=http.HTTP_403_FORBIDDEN)
        branch = profile.current_batch.course.department.branch
        return Response(report_i.student_summary(branch, profile))
