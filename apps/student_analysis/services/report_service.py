"""Aggregate student report from accounts, admissions, attendance, and examinations."""

from __future__ import annotations

import datetime
from collections import defaultdict
from decimal import Decimal

from apps.accounts.models.user import Role, User
from apps.accounts.models.profile import StudentProfile
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile
from apps.attendance.helpers import attendance_percent
from apps.attendance.models import AttendanceRecord
from apps.attendance.queries import record as record_q
from apps.attendance.queries import roster as roster_q
from apps.examinations.enums import MarksStatus
from apps.examinations.models import MarksEntry
from apps.examinations.queries import marks as marks_q
from apps.fees.queries.invoice import list_dues_for_student_user

_WIDE_FROM = datetime.date(1970, 1, 1)
_WIDE_TO = datetime.date(2999, 12, 31)

WEAK_MARKS_THRESHOLD = 40
STRONG_MARKS_THRESHOLD = 85
RISK_ATTENDANCE_THRESHOLD = 75
RISK_HIGH_MARKS_THRESHOLD = 50
RISK_MEDIUM_MARKS_THRESHOLD = 65


def get_student_report(roll_number: str, *, tenant_id=None) -> dict:
    """
    Build a structured analysis report for a student identified by roll number.

    Roll number is stored on User.custom_login_id (role=student).
    Attendance and exam marks are resolved via the active StudentEnrollment.
    """
    qs = User.objects.select_related("student_profile", "branch", "tenant").filter(
        custom_login_id=roll_number, role=Role.STUDENT, is_active=True,
    )
    if tenant_id is not None:
        qs = qs.filter(tenant_id=tenant_id)
    user = qs.first()
    if user is None:
        raise User.DoesNotExist(f"No active student found for roll number: {roll_number}")

    try:
        profile = user.student_profile
    except StudentProfile.DoesNotExist:
        profile = None

    enrollment = None
    if profile is not None:
        enrollment = profile.current_enrollment or get_active_enrollment_for_profile(profile.pk)

    attendance_records = _fetch_attendance_records(enrollment)
    marks_entries = _fetch_marks_entries(enrollment)

    average_attendance = _average_attendance(enrollment)
    average_marks = _average_marks(marks_entries)
    weak_subjects, strong_subjects = _classify_subjects(marks_entries)
    total_backlogs = _total_backlogs(enrollment)
    risk_score = _risk_score(
        average_marks,
        average_attendance,
        marks_count=len(marks_entries),
        attendance_count=len(attendance_records),
    )
    fees = _fees_summary(user)

    return {
        "rollNumber": roll_number,
        "student": {
            "userId": str(user.id),
            "name": user.full_name,
            "email": user.email,
            "phone": user.phone,
            "customLoginId": user.custom_login_id,
            "branchId": str(user.branch_id) if user.branch_id else None,
            "tenantId": str(user.tenant_id) if user.tenant_id else None,
        },
        "profile": _profile_payload(profile),
        "enrollment": _enrollment_payload(enrollment),
        "attendance": {
            "averagePercent": average_attendance,
            "totalRecords": len(attendance_records),
            "records": attendance_records,
        },
        "marks": {
            "averageMarks": average_marks,
            "totalEntries": len(marks_entries),
            "entries": marks_entries,
        },
        "fees": fees,
        "analysis": {
            "averageMarks": average_marks,
            "averageAttendance": average_attendance,
            "weakSubjects": weak_subjects,
            "strongSubjects": strong_subjects,
            "totalBacklogs": total_backlogs,
            "riskScore": risk_score,
            "totalDuePaise": fees["totalDuePaise"],
            "openInvoiceCount": fees["openInvoiceCount"],
        },
    }


def _profile_payload(profile) -> dict | None:
    if profile is None:
        return None
    return {
        "profileId": str(profile.id),
        "gender": profile.gender,
        "dateOfBirth": profile.date_of_birth.isoformat() if profile.date_of_birth else None,
        "bloodGroup": profile.blood_group,
        "address": profile.address,
        "nationality": profile.nationality,
        "religion": profile.religion,
        "admissionDate": profile.admission_date.isoformat() if profile.admission_date else None,
        "academicStatus": profile.academic_status,
        "batchId": str(profile.current_batch_id) if profile.current_batch_id else None,
    }


def _enrollment_payload(enrollment) -> dict | None:
    if enrollment is None:
        return None
    return {
        "enrollmentId": str(enrollment.id),
        "status": enrollment.status,
        "batchId": str(enrollment.batch_id) if enrollment.batch_id else None,
        "batchName": enrollment.batch.name if enrollment.batch_id else None,
        "academicYearId": str(enrollment.academic_year_id),
        "academicYearName": enrollment.academic_year.name,
        "branchId": str(enrollment.branch_id),
    }


def _fetch_attendance_records(enrollment) -> list[dict]:
    if enrollment is None:
        return []
    qs = (
        AttendanceRecord.objects.filter(student_id=enrollment.pk, is_active=True)
        .select_related("session")
        .order_by("-marked_at")
    )
    return [
        {
            "recordId": str(record.id),
            "sessionId": str(record.session_id),
            "date": record.session.date.isoformat(),
            "status": record.status,
            "markedAt": record.marked_at.isoformat(),
            "lateMark": record.late_mark,
        }
        for record in qs
    ]


def _fetch_marks_entries(enrollment) -> list[dict]:
    if enrollment is None:
        return []
    qs = (
        MarksEntry.objects.filter(
            student_id=enrollment.pk,
            is_active=True,
            marks_status__in=[MarksStatus.SUBMITTED, MarksStatus.LOCKED],
        )
        .select_related("subject", "exam")
        .order_by("-created_at")
    )
    return [
        {
            "entryId": str(entry.id),
            "examId": str(entry.exam_id),
            "examName": entry.exam.name,
            "subjectId": str(entry.subject_id),
            "subjectName": entry.subject.name,
            "marks": float(entry.marks) if entry.marks is not None else None,
            "isAbsent": entry.is_absent,
            "isInternal": entry.is_internal,
            "graceApplied": float(entry.grace_applied or Decimal("0")),
            "marksStatus": entry.marks_status,
        }
        for entry in qs
    ]


def _average_attendance(enrollment) -> float:
    if enrollment is None:
        return 0.0
    _, exam_counts = roster_q.attendance_config(enrollment.branch)
    present_like, excused, total = record_q.aggregate_counts(
        enrollment.pk,
        date_from=_WIDE_FROM,
        date_to=_WIDE_TO,
        exclude_exam_days=not exam_counts,
    )
    return attendance_percent(present_like, excused, total)


def _average_marks(marks_entries: list[dict]) -> float:
    values = [
        entry["marks"]
        for entry in marks_entries
        if entry["marks"] is not None and not entry["isAbsent"]
    ]
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _classify_subjects(marks_entries: list[dict]) -> tuple[list[dict], list[dict]]:
    by_subject: dict[str, list[float]] = defaultdict(list)
    subject_names: dict[str, str] = {}

    for entry in marks_entries:
        if entry["marks"] is None or entry["isAbsent"]:
            continue
        sid = entry["subjectId"]
        by_subject[sid].append(entry["marks"])
        subject_names[sid] = entry["subjectName"]

    weak_subjects: list[dict] = []
    strong_subjects: list[dict] = []

    for subject_id, values in by_subject.items():
        average = round(sum(values) / len(values), 2)
        payload = {
            "subjectId": subject_id,
            "subjectName": subject_names[subject_id],
            "averageMarks": average,
        }
        if average < WEAK_MARKS_THRESHOLD:
            weak_subjects.append(payload)
        elif average > STRONG_MARKS_THRESHOLD:
            strong_subjects.append(payload)

    weak_subjects.sort(key=lambda item: item["averageMarks"])
    strong_subjects.sort(key=lambda item: item["averageMarks"], reverse=True)
    return weak_subjects, strong_subjects


def _total_backlogs(enrollment) -> int:
    if enrollment is None:
        return 0

    backlog_subject_ids: set[str] = set()
    for item in enrollment.backlog_subjects or []:
        subject_id = item.get("subjectId") or item.get("subject_id")
        if subject_id:
            backlog_subject_ids.add(str(subject_id))

    for arrear in marks_q.open_arrear_subjects(enrollment.pk):
        backlog_subject_ids.add(arrear["subjectId"])

    return len(backlog_subject_ids)


def _fees_summary(user: User) -> dict:
    invoices = list(list_dues_for_student_user(user.id))
    open_invoices = [inv for inv in invoices if inv.balance_paise > 0]
    total_due = sum(inv.balance_paise for inv in open_invoices)
    return {
        "totalDuePaise": total_due,
        "openInvoiceCount": len(open_invoices),
        "invoices": [
            {
                "invoiceId": str(inv.id),
                "label": _invoice_label(inv),
                "totalPaise": inv.total_paise,
                "paidPaise": inv.paid_paise,
                "balancePaise": inv.balance_paise,
                "status": inv.status,
                "dueDate": inv.due_date.isoformat() if inv.due_date else None,
            }
            for inv in invoices[:12]
        ],
    }


def _invoice_label(invoice) -> str:
    first_line = invoice.lines.first()
    if first_line:
        return first_line.label
    return f"Invoice {str(invoice.id)[:8]}"


def _risk_score(
    average_marks: float,
    average_attendance: float,
    *,
    marks_count: int,
    attendance_count: int,
) -> str:
    if marks_count == 0 and attendance_count == 0:
        return "unknown"
    if marks_count == 0:
        if average_attendance < RISK_ATTENDANCE_THRESHOLD:
            return "high"
        return "medium"
    if attendance_count == 0:
        if average_marks < RISK_HIGH_MARKS_THRESHOLD:
            return "high"
        if average_marks < RISK_MEDIUM_MARKS_THRESHOLD:
            return "medium"
        return "low"
    if average_marks < RISK_HIGH_MARKS_THRESHOLD or average_attendance < RISK_ATTENDANCE_THRESHOLD:
        return "high"
    if average_marks < RISK_MEDIUM_MARKS_THRESHOLD:
        return "medium"
    return "low"
