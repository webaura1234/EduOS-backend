"""Interactors — role dashboards (read aggregates).

Composes the other modules through THEIR query/interactor layers — analytics adds no
cross-app ORM (architecture rule). Computed live per request (OD-1); the view stamps
`X-Cache-Age` / `lastUpdated`.
"""

from apps.accounts.queries.user import count_active_by_role_in_tenant
from apps.accounts.models.user import Role
from apps.admissions.queries.enquiry import funnel_counts
from apps.attendance.interactors import report as att_report
from apps.fees.interactors.report import GetCollectionDashboardInteractor
from apps.fees.queries.defaulter import list_defaulters
from apps.grievances.queries import count_open as count_open_grievances
from apps.hr.queries.leave import count_pending_applications, leave_summary
from apps.organizations.queries.branch import list_branches
from django.utils import timezone
from apps.academics.helpers import is_college
from apps.admissions.queries import enrollment as enrollment_q
from apps.attendance.interactors.report import student_summary
from apps.fees.queries.invoice import list_dues_for_student_user
from apps.academics.queries import timetable as tt_q
from apps.examinations.interactors.hub import build_exam_hub


def collection_dashboard(branch) -> dict:
    """F-138 — real-time fee collection metrics for a branch."""
    return GetCollectionDashboardInteractor(branch.pk).execute()


def admin_dashboard(branch, tenant) -> dict:
    """F-051 / F-053 — admin snapshot + alerts for one branch."""
    fees = GetCollectionDashboardInteractor(branch.pk).execute()
    shortage = att_report.shortage_report(branch)
    defaulters = list(list_defaulters(branch.pk))
    pending_leave = count_pending_applications(branch.pk)
    open_grievances = count_open_grievances(branch.pk)
    return {
        "fees": fees,
        "alerts": {
            "lowAttendanceCount": len(shortage["rows"]),
            "lowAttendance": shortage["rows"][:10],
            "pendingFeesCount": len(defaulters),
            "pendingHrLeaveCount": pending_leave,
            "openGrievancesCount": open_grievances,
            "attendanceThreshold": shortage["threshold"],
        },
        "admissionsFunnel": funnel_counts(branch.pk),
        "leaveSummary": leave_summary(branch.pk),
    }


def super_admin_dashboard(tenant) -> dict:
    """F-021/022/025/038/039 — consolidated + per-branch comparison across the tenant."""
    branches = list(list_branches(tenant.pk))
    per_branch = []
    total_collected = total_invoiced = total_low_attendance = 0
    consolidated_defaulters = []
    for b in branches:
        fees = GetCollectionDashboardInteractor(b.pk).execute()
        shortage = att_report.shortage_report(b)
        defaulters = list(list_defaulters(b.pk))
        total_collected += fees["totalCollectedPaise"]
        total_invoiced += fees["totalInvoicedPaise"]
        total_low_attendance += len(shortage["rows"])
        consolidated_defaulters.append({"branchId": str(b.pk), "branchName": b.name,
                                        "defaulterCount": len(defaulters)})
        per_branch.append({
            "branchId": str(b.pk),
            "branchName": b.name,
            "collectedPaise": fees["totalCollectedPaise"],
            "pendingPaise": fees["totalPendingPaise"],
            "lowAttendanceCount": len(shortage["rows"]),
        })
    return {
        "totals": {
            "branches": len(branches),
            "students": count_active_by_role_in_tenant(tenant.pk, Role.STUDENT),
            "faculty": count_active_by_role_in_tenant(tenant.pk, Role.FACULTY),
            "collectedPaise": total_collected,
            "invoicedPaise": total_invoiced,
            "pendingPaise": max(total_invoiced - total_collected, 0),
            "lowAttendanceCount": total_low_attendance,
        },
        "branchComparison": per_branch,
        "consolidatedDefaulters": consolidated_defaulters,
    }


def student_dashboard(user) -> dict:
    """F-196 — Real-time dashboard composition for a student caller (caller-scoped, D6)."""
    # 1. Resolve student profile
    profile = getattr(user, "student_profile", None)
    tenant = user.tenant
    institution_type = "college" if is_college(tenant) else "school"

    if not profile:
        return {
            "institutionType": institution_type,
            "profile": {
                "name": user.full_name,
                "classLabel": "—",
            },
            "attendancePercent": 0,
            "attendanceThreshold": 75,
            "attendanceAlert": None,
            "feeAlert": None,
            "scheduleToday": [],
            "upcomingExamsCount": 0,
            "nextExamLabel": None,
            "hallTicketAvailable": False,
            "announcements": [],
        }

    # 2. Resolve active enrollment
    enrollment = enrollment_q.resolve_enrollment_for_profile(profile)
    if not enrollment:
        return {
            "institutionType": institution_type,
            "profile": {
                "name": user.full_name,
                "classLabel": "—",
            },
            "attendancePercent": 0,
            "attendanceThreshold": 75,
            "attendanceAlert": None,
            "feeAlert": None,
            "scheduleToday": [],
            "upcomingExamsCount": 0,
            "nextExamLabel": None,
            "hallTicketAvailable": False,
            "announcements": [],
        }

    # 3. Profile details
    batch = enrollment.batch
    branch = enrollment.branch
    class_label = f"{batch.course.name} - {batch.name}" if batch else "—"

    # 4. Attendance summary & alert
    summary = student_summary(branch, enrollment)
    attendance_pct = summary["overallPercent"]
    threshold = summary["threshold"]
    attendance_alert = None
    if attendance_pct < threshold:
        attendance_alert = {
            "level": "critical",
            "message": f"Attendance is {attendance_pct}% — below the required {threshold}%. You may be barred from exams.",
            "attendancePercent": attendance_pct,
            "thresholdPercent": threshold,
        }
    elif attendance_pct < threshold + 5:
        attendance_alert = {
            "level": "warning",
            "message": f"Attendance is {attendance_pct}%, approaching the {threshold}% minimum. Improve attendance to stay eligible.",
            "attendancePercent": attendance_pct,
            "thresholdPercent": threshold,
        }

    # 5. Fee balance & alert
    invoices = list_dues_for_student_user(user.pk)
    total_balance_paise = sum((inv.total_paise - inv.paid_paise) for inv in invoices)
    fee_balance = total_balance_paise / 100
    fee_alert = None
    if fee_balance > 0:
        fee_alert = {
            "message": f"Fee balance due: ₹{fee_balance:,.0f}",
            "amountDue": fee_balance,
        }

    # 6. Today's schedule
    schedule_today = []
    today = timezone.localdate()
    day_of_week = today.isoweekday()
    if batch:
        timetables = list(tt_q.list_timetables(branch_id=branch.pk, batch_id=batch.pk))
        published_tt = next((tt for tt in timetables if tt.is_published), None)
        if published_tt:
            entries = (
                tt_q.list_timetable_entries(published_tt.pk)
                .filter(day_of_week=day_of_week)
                .order_by("period_slot__sequence")
            )
            for entry in entries:
                schedule_today.append({
                    "startTime": entry.period_slot.start_time.strftime("%H:%M"),
                    "endTime": entry.period_slot.end_time.strftime("%H:%M"),
                    "subjectName": entry.batch_subject.subject.name,
                    "roomName": entry.room.name if entry.room else "—",
                    "dayLabel": entry.get_day_of_week_display(),
                })

    # 7. Upcoming exams & hall ticket (composes build_exam_hub)
    exam_hub = build_exam_hub(profile, tenant=tenant)
    upcoming_exams = exam_hub.get("upcomingExams", [])
    upcoming_exams_count = len(upcoming_exams)
    next_exam = upcoming_exams[0] if upcoming_exams else None
    next_exam_label = None
    if next_exam:
        next_exam_label = f"{next_exam['name']} · {next_exam['date']}"

    return {
        "institutionType": institution_type,
        "profile": {
            "name": user.full_name,
            "classLabel": class_label,
        },
        "attendancePercent": attendance_pct,
        "attendanceThreshold": threshold,
        "attendanceAlert": attendance_alert,
        "feeAlert": fee_alert,
        "scheduleToday": schedule_today,
        "upcomingExamsCount": upcoming_exams_count,
        "nextExamLabel": next_exam_label,
        "hallTicketAvailable": exam_hub.get("hallTicketAvailable", False),
        "announcements": [],
    }
