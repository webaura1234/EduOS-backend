"""Admin Attendance overview — the AttendanceData aggregate the admin screen consumes."""

import datetime

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries.structure import list_batches
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.attendance.interactors import report as report_i
from apps.attendance.queries import audit as audit_q
from apps.attendance.queries import leave as leave_q
from apps.attendance.queries import record as record_q
from apps.attendance.queries import roster as roster_q
from apps.attendance.queries import session as session_q

# FE AttendanceStatus has no "flagged"; coerce anything unexpected to "absent".
_FE_STATUSES = {"present", "absent", "late", "leave", "excused"}


def _status(value) -> str:
    return value if value in _FE_STATUSES else "absent"


def _live_snapshot(branch) -> dict:
    today = datetime.date.today()
    by_batch: dict[str, dict] = {}
    present_total = total_total = 0
    for s in session_q.list_sessions_for_date(branch.pk, today):
        counts = record_q.status_counts_for_session(s.pk)
        present = counts.get("present", 0) + counts.get("late", 0)
        total = sum(counts.values())
        bid = str(s.batch_id)
        entry = by_batch.setdefault(
            bid, {"classId": bid, "classLabel": s.batch.name, "present": 0, "total": 0}
        )
        entry["present"] += present
        entry["total"] += total
        present_total += present
        total_total += total
    percent = round(present_total / total_total * 100) if total_total else 0
    return {
        "present": present_total,
        "total": total_total,
        "percent": percent,
        "classes": list(by_batch.values()),
        "updatedAt": timezone.now().isoformat(),
    }


def _record(r) -> dict:
    sess = r.session
    has_subject = sess.batch_subject_id is not None
    return {
        "id": str(r.pk),
        "studentId": str(r.student.student_profile_id),
        "studentName": r.student.user.full_name,
        "rollNumber": r.student.user.custom_login_id or "",
        "classSectionId": str(sess.batch_id),
        "classLabel": sess.batch.name,
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


def _leave(lv) -> dict:
    student = lv.student
    has_batch = student and student.current_batch_id
    return {
        "id": str(lv.pk),
        "studentId": str(student.student_profile_id) if student else "",
        "studentName": student.user.full_name if student else "",
        "classSectionId": str(student.current_batch_id) if has_batch else "",
        "classLabel": student.current_batch.name if has_batch else "",
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
        "classLabel": sess.batch.name if sess else "",
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
        rows.append({
            "studentId": row["studentId"],
            "studentName": row["name"],
            "classLabel": batch_names.get(row.get("batchId") or "", ""),
            "presentDays": round(pct * sessions / 100),
            "totalDays": sessions,
            "percent": pct,
            "thresholdPercent": threshold,
        })
    return rows


def _monthly_student_rows(report: dict, student_class: dict) -> list:
    """Per-student monthly attendance rows (MonthlyStudentReportRow shape)."""
    month_label = f"{report['year']}-{report['month']:02d}"
    rows = []
    for row in report.get("rows", []):
        sessions = row.get("sessions", 0)
        pct = row.get("percent", 0)
        rows.append({
            "month": month_label,
            "studentId": row["studentId"],
            "studentName": row["name"],
            "classLabel": student_class.get(row["studentId"], ""),
            "presentDays": round(pct * sessions / 100),
            "totalDays": sessions,
            "percent": pct,
        })
    return rows


class AdminAttendanceOverviewView(APIView):
    """GET → AttendanceData { live, rules, records, leaveRequests, auditLog,
    shortageReport, detentionList, monthlyReports }."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        threshold, exam_counts = roster_q.attendance_config(branch)
        batch_names = {str(b.id): b.name for b in list_batches(branch.pk)}

        # studentProfileId → class label, for rows that only carry a student id.
        student_class = {
            str(sp.student_profile_id): (sp.current_batch.name if sp.current_batch_id else "")
            for sp in roster_q.all_active_students_in_branch(branch.pk)
        }

        records = [_record(r) for r in record_q.list_records_for_branch(branch.pk)]
        leaves = [_leave(lv) for lv in leave_q.list_leaves(branch.pk) if lv.student_id]
        audits = [_audit(a) for a in audit_q.list_audits(branch.pk)[:100]]

        shortage = _shortage_rows(report_i.shortage_report(branch), batch_names)
        detention = _shortage_rows(report_i.detention_report(branch), batch_names)

        today = datetime.date.today()
        monthly = report_i.monthly_report(branch, year=today.year, month=today.month)
        monthly_rows = _monthly_student_rows(monthly, student_class)

        return Response({
            "live": _live_snapshot(branch),
            "rules": {
                "thresholdPercent": threshold,
                "examDayCountsTowardThreshold": exam_counts,
            },
            "records": records,
            "leaveRequests": leaves,
            "auditLog": audits,
            "shortageReport": shortage,
            "detentionList": detention,
            "monthlyReports": monthly_rows,
        })


class AdminAttendanceLiveView(APIView):
    """GET → LiveAttendanceSnapshot (the polled live tab)."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        return Response(_live_snapshot(resolve_branch(request)))
