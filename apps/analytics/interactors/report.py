"""Interactors — report generation with snapshot-at-request + small/large execution.

Small reports resolve inline (frozen snapshot, F-064); large ones dispatch a Celery task
that serializes to CSV and uploads to S3 (OD-2). Rows are always resolved at request time
through the owning module's query layer (no cross-app ORM here).
"""

from django.utils import timezone

from apps.accounts.models.user import Role
from apps.accounts.queries.user import count_active_by_role_in_tenant
from apps.admissions.queries.enquiry import funnel_counts
from apps.analytics.enums import ReportStatus, ReportType
from apps.analytics.queries import report as report_q
from apps.attendance.interactors import report as att_report
from apps.fees.queries.defaulter import list_defaulters
from apps.hr.queries.leave import leave_summary

DEFAULT_THRESHOLD = 500


def _resolve_rows(report_type, branch, params) -> list[dict]:
    """Request-time snapshot of the report rows (F-064), via module query layers."""
    if report_type == ReportType.FEE_DEFAULTERS:
        return [
            {"invoiceId": str(inv.pk), "studentProfileId": str(inv.student.student_profile_id),
             "dueDate": inv.due_date.isoformat() if inv.due_date else None,
             "balancePaise": inv.total_paise - inv.paid_paise}
            for inv in list_defaulters(branch.pk)
        ]
    if report_type == ReportType.ADMISSION_FUNNEL:
        f = funnel_counts(branch.pk)
        return [{"dimension": k, **{"k": kk, "n": vv}} for k, d in f.items() for kk, vv in d.items()]
    if report_type == ReportType.HR_LEAVE_SUMMARY:
        return leave_summary(branch.pk)["rows"]
    if report_type == ReportType.ATTENDANCE_MONTHLY:
        year = int(params.get("year", timezone.now().year))
        month = int(params.get("month", timezone.now().month))
        return att_report.monthly_report(branch, year=year, month=month)["rows"]
    return []


def generate_report(*, tenant, branch, report_type, params=None, requester=None,
                    threshold=DEFAULT_THRESHOLD):
    """Create a ReportExport. Small → inline ready; large → queued Celery job."""
    params = params or {}
    export = report_q.create_export(
        tenant=tenant, branch=branch, report_type=report_type, params=params,
        requested_by=requester,
    )
    rows = _resolve_rows(report_type, branch, params)  # request-time snapshot
    report_q.update_export(export, {
        "snapshot": {"rows": rows}, "row_count": len(rows),
    }, user=requester)

    if len(rows) <= threshold:
        report_q.update_export(export, {
            "status": ReportStatus.READY,
            "expires_at": timezone.now() + timezone.timedelta(hours=24),
        }, user=requester)
    else:
        report_q.update_export(export, {"status": ReportStatus.QUEUED}, user=requester)
        from apps.analytics.tasks import generate_export_task
        generate_export_task.delay(str(export.pk))

    export.refresh_from_db()
    return export


def naac_export(*, tenant, branch) -> dict:
    """F-048 / F-237 — accreditation export that lists missing fields but still exports."""
    data = {
        "studentsCount": count_active_by_role_in_tenant(tenant.pk, Role.STUDENT),
        "facultyCount": count_active_by_role_in_tenant(tenant.pk, Role.FACULTY),
        "branchName": branch.name,
    }
    # Phase-1: accreditation-specific criteria are not yet captured → reported as gaps.
    missing = ["studentTeacherRatioCriteria", "researchOutput", "infrastructureScore"]
    return {"data": data, "missingFields": missing}
