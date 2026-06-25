"""Admin Attendance overview — the AttendanceData aggregate the admin screen consumes."""

import datetime

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.helpers import batch_display_label
from apps.academics.queries.structure import list_batches
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.attendance.interactors import live_board as live_i
from apps.attendance.interactors import report as report_i
from apps.attendance.queries import audit as audit_q
from apps.attendance.queries import leave as leave_q
from apps.attendance.queries import record as record_q
from apps.attendance.queries import roster as roster_q
from apps.attendance.helpers import (
    current_iso_week,
    month_bounds,
    parse_month_param,
    parse_week_param,
)

# FE AttendanceStatus has no "flagged"; coerce anything unexpected to "absent".
_FE_STATUSES = {"present", "absent", "late", "leave", "excused"}


def _status(value) -> str:
    return value if value in _FE_STATUSES else "absent"


def _live_snapshot(branch) -> dict:
    return live_i.branch_live_snapshot(branch)


def _record(r) -> dict:
    sess = r.session
    has_subject = sess.batch_subject_id is not None
    return {
        "id": str(r.pk),
        "studentId": str(r.student.student_profile_id),
        "studentName": r.student.user.full_name,
        "rollNumber": r.student.user.custom_login_id or "",
        "classSectionId": str(sess.batch_id),
        "classLabel": batch_display_label(sess.batch),
        "subjectId": str(sess.batch_subject.subject_id) if has_subject else "",
        "subjectName": sess.batch_subject.subject.name if has_subject else "",
        "date": sess.date.isoformat(),
        "status": _status(r.status),
        "markedAt": r.marked_at.isoformat() if r.marked_at else "",
        "markedByUserId": str(r.marked_by_id) if r.marked_by_id else "",
        "classEndTime": sess.period_slot.end_time.isoformat() if sess.period_slot_id else "",
        "isExamDay": sess.is_exam_day,
        "geoFlagged": r.status == "flagged",
        "geoFlagReason": None,
    }


def _class_section(b) -> dict:
    return {
        "id": str(b.id),
        "label": batch_display_label(b),
        "departmentId": str(b.course.department_id),
        "courseId": str(b.course_id),
        "grade": b.course.name,
        "section": b.name,
        "academicYearId": str(b.academic_year_id),
    }


def _leave(lv) -> dict:
    student = lv.student
    batch = student.batch if student and student.batch_id else None
    return {
        "id": str(lv.pk),
        "studentId": str(student.student_profile_id) if student else "",
        "studentName": student.user.full_name if student else "",
        "classSectionId": str(batch.pk) if batch else "",
        "classLabel": batch_display_label(batch) if batch else "",
        "fromDate": lv.from_date.isoformat(),
        "toDate": lv.to_date.isoformat(),
        "reason": lv.reason,
        "status": lv.status if lv.status in ("pending", "approved", "rejected") else "pending",
        "appliedByRole": "parent" if lv.applicant_role == "parent" else "student",
        "appliedByName": lv.applied_by.full_name if lv.applied_by_id else "",
        "appliedAt": lv.created_at.isoformat(),
        "reviewedByUserId": str(lv.approver_id) if lv.approver_id else None,
        "reviewedByName": lv.approver.full_name if lv.approver_id else None,
        "reviewedAt": lv.approved_at.isoformat() if lv.approved_at else None,
        "reviewNote": lv.decision_note or None,
    }


def _audit(a) -> dict:
    rec = a.record
    sess = rec.session if rec else None
    has_subject = sess and sess.batch_subject_id
    return {
        "id": str(a.pk),
        "type": a.audit_type,
        "recordId": str(a.record_id) if a.record_id else "",
        "studentName": rec.student.user.full_name if rec else "",
        "classLabel": batch_display_label(sess.batch) if sess else "",
        "subjectName": sess.batch_subject.subject.name if has_subject else "",
        "date": sess.date.isoformat() if sess else "",
        "originalStatus": _status(a.original_status) if a.original_status else None,
        "newStatus": _status(a.new_status) if a.new_status else None,
        "editedByUserId": str(a.actor_id) if a.actor_id else "",
        "createdAt": a.created_at.isoformat(),
        "note": a.reason or "",
    }


def _shortage_rows(report: dict, batch_names: dict) -> list:
    threshold = report.get("threshold", 0)
    rows = []
    for row in report.get("rows", []):
        sessions = row.get("sessions", 0)
        pct = row.get("percent", 0)
        batch_id = row.get("batchId") or ""
        rows.append({
            "studentId": row["studentId"],
            "studentName": row["name"],
            "classSectionId": batch_id,
            "classLabel": batch_names.get(batch_id, ""),
            "presentDays": round(pct * sessions / 100),
            "totalDays": sessions,
            "percent": pct,
            "thresholdPercent": threshold,
        })
    return rows


def _period_student_rows(report: dict, batch_names: dict, *, period_label: str) -> list:
    """Per-student rows for weekly/monthly period tables."""
    rows = []
    for row in report.get("rows", []):
        sessions = row.get("sessions", 0)
        pct = row.get("percent", 0)
        batch_id = row.get("batchId") or ""
        rows.append({
            "period": period_label,
            "studentId": row["studentId"],
            "studentName": row["name"],
            "classSectionId": batch_id,
            "classLabel": batch_names.get(batch_id, ""),
            "presentDays": round(pct * sessions / 100),
            "totalDays": sessions,
            "percent": pct,
        })
    return rows


def _resolve_report_range(request) -> tuple[datetime.date, datetime.date, str, dict]:
    """Return (date_from, date_to, period_label, report_filters dict)."""
    period = request.query_params.get("period", "monthly")
    batch_id = request.query_params.get("batchId") or None

    if period == "weekly":
        week_param = request.query_params.get("week")
        if week_param:
            date_from, date_to = parse_week_param(week_param)
            week_label = week_param.upper() if "-W" in week_param.upper() else date_from.isoformat()
        else:
            year, week = current_iso_week()
            date_from, date_to = datetime.date.fromisocalendar(year, week, 1), datetime.date.fromisocalendar(year, week, 7)
            week_label = f"{year}-W{week:02d}"
        filters = {
            "period": "weekly",
            "week": week_label,
            "batchId": batch_id,
            "dateFrom": date_from.isoformat(),
            "dateTo": date_to.isoformat(),
        }
        return date_from, date_to, week_label, filters

    month_param = request.query_params.get("month")
    if month_param:
        date_from, date_to = parse_month_param(month_param)
        month_label = month_param
    else:
        today = datetime.date.today()
        date_from, date_to = month_bounds(today.year, today.month)
        month_label = f"{today.year}-{today.month:02d}"
    filters = {
        "period": "monthly",
        "month": month_label,
        "batchId": batch_id,
        "dateFrom": date_from.isoformat(),
        "dateTo": date_to.isoformat(),
    }
    return date_from, date_to, month_label, filters


class AdminAttendanceOverviewView(APIView):
    """GET → AttendanceData { live, rules, records, leaveRequests, auditLog,
    shortageReport, detentionList, periodReports, reportFilters }."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        threshold, exam_counts = roster_q.attendance_config(branch)
        batch_names = {str(b.id): batch_display_label(b) for b in list_batches(branch.pk)}
        batches = list(list_batches(branch.pk))

        records = [_record(r) for r in record_q.list_records_for_branch(branch.pk)]
        leaves = [_leave(lv) for lv in leave_q.list_leaves(branch.pk) if lv.student_id]
        audits = [_audit(a) for a in audit_q.list_audits(branch.pk)[:100]]

        date_from, date_to, period_label, report_filters = _resolve_report_range(request)
        batch_id = report_filters.get("batchId")

        ranking = report_i.ranking_report(
            branch, date_from=date_from, date_to=date_to, batch_id=batch_id
        )
        shortage = _shortage_rows(ranking, batch_names)
        detention = _shortage_rows(
            report_i.detention_report(
                branch, batch_id=batch_id, date_from=date_from, date_to=date_to
            ),
            batch_names,
        )
        period_rows = _period_student_rows(ranking, batch_names, period_label=period_label)

        return Response({
            "live": _live_snapshot(branch),
            "rules": {
                "thresholdPercent": threshold,
                "examDayCountsTowardThreshold": exam_counts,
            },
            "records": records,
            "leaveRequests": leaves,
            "classSections": [_class_section(b) for b in batches],
            "auditLog": audits,
            "shortageReport": shortage,
            "detentionList": detention,
            "periodReports": period_rows,
            "reportFilters": report_filters,
        })


class AdminAttendanceLiveView(APIView):
    """GET → LiveAttendanceSnapshot (the polled live tab)."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        return Response(_live_snapshot(resolve_branch(request)))
