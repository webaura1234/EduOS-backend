"""Interactors — role dashboards (read aggregates).

Composes the other modules through THEIR query/interactor layers — analytics adds no
cross-app ORM (architecture rule).

The consolidated admin / super-admin rollups fan out across every branch (fees,
attendance, defaulters, staff attendance), which is expensive. They are memoised in
the shared cache for a short TTL keyed by branch/tenant; the view surfaces the real
cache age via `X-Cache-Age` / `lastUpdated` so the UI can show "last updated". Per-user
and single-branch dashboards stay live (no cache).
"""

from django.conf import settings
from django.core.cache import cache

from apps.accounts.queries.user import (
    count_active_by_role_grouped_by_branch,
    count_active_by_role_in_tenant,
)
from apps.accounts.models.user import Role
from apps.admissions.queries.enquiry import funnel_counts
from apps.attendance.interactors import report as att_report
from apps.attendance.queries import roster as roster_q
from apps.fees.interactors.report import GetCollectionDashboardInteractor
from apps.fees.queries.defaulter import list_defaulters
from apps.grievances.queries import count_open as count_open_grievances
from apps.hr.queries import employee as emp_q
from apps.hr.queries import staff_attendance as sa_q
from apps.hr.queries.leave import count_pending_applications, leave_summary
from apps.organizations.queries.branch import list_branches
from django.utils import timezone
from apps.academics.helpers import is_college
from apps.admissions.queries import enrollment as enrollment_q
from apps.attendance.interactors.report import student_summary
from apps.fees.queries.invoice import list_dues_for_student_user
from apps.academics.queries import timetable as tt_q
from apps.examinations.interactors.hub import build_exam_hub


# Very short memoisation window for the expensive consolidated rollups. Its only job
# now (after the per-branch fan-out was batched) is to coalesce the burst a single
# dashboard load produces — the dashboard panel and the alerts banner hit this same
# tenant/branch computation in parallel — plus rapid back-and-forth navigation. Kept
# small so the dashboard reflects DB changes near-instantly; the UI still shows the
# real age via X-Cache-Age. Tunable per environment.
DASHBOARD_CACHE_TTL = getattr(settings, "DASHBOARD_CACHE_TTL_SECONDS", 10)


def _get_or_compute(cache_key: str, compute):
    """Return ``(data, computed_at)``, memoising ``compute()`` for ``DASHBOARD_CACHE_TTL``.

    ``computed_at`` is the timezone-aware moment the cached payload was produced, so the
    view can report real cache age instead of a hardcoded zero.
    """
    hit = cache.get(cache_key)
    if hit is not None:
        data, computed_at = hit
        return data, computed_at
    data = compute()
    computed_at = timezone.now()
    cache.set(cache_key, (data, computed_at), DASHBOARD_CACHE_TTL)
    return data, computed_at


def collection_dashboard(branch) -> dict:
    """F-138 — real-time fee collection metrics for a branch."""
    return GetCollectionDashboardInteractor(branch.pk).execute()


def admin_dashboard(branch, tenant):
    """F-051 / F-053 — admin snapshot + alerts for one branch. Returns ``(data, computed_at)``."""
    return _get_or_compute(
        f"dashboard:admin:{branch.pk}",
        lambda: _compute_admin_dashboard(branch, tenant),
    )


def _compute_admin_dashboard(branch, tenant) -> dict:
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


def _branch_faculty_attendance_percents(branches) -> dict:
    """Average faculty staff-attendance % (current month) per branch: ``{branch_pk: percent}``.

    ONE grouped staff-attendance query for all faculty across every branch (was one per
    branch). Identical value to averaging each branch's faculty monthly percentages —
    faculty belong to a single branch, so the per-branch id lists are disjoint.
    """
    branches = list(branches)
    today = timezone.localdate()
    ids_by_branch = {}
    all_ids = []
    for b in branches:
        ids = [e.user_id for e in emp_q.list_employees(b.pk)]
        ids.extend(u.pk for u in emp_q.list_faculty_without_employee(b.pk))
        ids_by_branch[b.pk] = ids
        all_ids.extend(ids)

    percents = (
        sa_q.month_attendance_percent_by_user(all_ids, today.year, today.month)
        if all_ids
        else {}
    )

    result = {}
    for b in branches:
        ids = ids_by_branch[b.pk]
        if not ids:
            result[b.pk] = 0
            continue
        values = [percents.get(uid, 0) for uid in ids]
        result[b.pk] = round(sum(values) / len(values))
    return result


def super_admin_dashboard(tenant):
    """F-021/022/025/038/039 — consolidated + per-branch comparison. Returns ``(data, computed_at)``."""
    return _get_or_compute(
        f"dashboard:super:{tenant.pk}",
        lambda: _compute_super_admin_dashboard(tenant),
    )


def _compute_super_admin_dashboard(tenant) -> dict:
    branches = list(list_branches(tenant.pk))
    # Batch the per-branch head-counts into one grouped query each (avoids a
    # student- and faculty-count round-trip per branch in the loop below).
    branch_ids = [b.pk for b in branches]
    student_counts = roster_q.active_student_counts_by_branch(branch_ids)
    faculty_counts = count_active_by_role_grouped_by_branch(tenant.pk, Role.FACULTY)
    # Student attendance % AND low-attendance count for every branch from ONE
    # aggregate scan (was one full-range ranking_report + one full-range
    # shortage_report per branch — the dashboard's dominant cost).
    attendance_summary = att_report.branch_attendance_summary(branches)
    # Faculty staff-attendance % for every branch in one grouped query too.
    faculty_attendance_percents = _branch_faculty_attendance_percents(branches)
    per_branch = []
    total_collected = total_invoiced = total_low_attendance = 0
    consolidated_defaulters = []
    for b in branches:
        fees = GetCollectionDashboardInteractor(b.pk).execute()
        low_attendance_count = attendance_summary.get(b.pk, {}).get("lowAttendanceCount", 0)
        defaulters = list(list_defaulters(b.pk))
        total_collected += fees["totalCollectedPaise"]
        total_invoiced += fees["totalInvoicedPaise"]
        total_low_attendance += low_attendance_count
        consolidated_defaulters.append({"branchId": str(b.pk), "branchName": b.name,
                                        "defaulterCount": len(defaulters)})
        per_branch.append({
            "branchId": str(b.pk),
            "branchName": b.name,
            "collectedPaise": fees["totalCollectedPaise"],
            "pendingPaise": fees["totalPendingPaise"],
            "lowAttendanceCount": low_attendance_count,
            "studentCount": student_counts.get(b.pk, 0),
            "facultyCount": faculty_counts.get(b.pk, 0),
            "attendancePercent": attendance_summary.get(b.pk, {}).get("percent", 0),
            "facultyAttendancePercent": faculty_attendance_percents.get(b.pk, 0),
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
