"""Interactors — report generation with snapshot-at-request + small/large execution.

Small reports resolve inline (frozen snapshot, F-064); large ones dispatch a Celery task
that serializes to CSV and uploads to S3 (OD-2). Rows are always resolved at request time
through the owning module's query layer (no cross-app ORM here).
"""

import datetime

from django.utils import timezone

from apps.accounts.models.user import Role
from apps.accounts.queries.user import count_active_by_role_in_tenant
from apps.admissions.queries.enquiry import funnel_counts
from apps.analytics.enums import ReportStatus, ReportType
from apps.analytics.queries import report as report_q
from apps.attendance.interactors import report as att_report
from apps.hr.queries.leave import leave_summary

DEFAULT_THRESHOLD = 500


def _parse_date(value, default):
    if not value:
        return default
    if isinstance(value, datetime.date):
        return value
    return datetime.date.fromisoformat(value)


def _branch_summary_rows(tenant) -> list[dict]:
    from apps.organizations.queries.branch import list_branches

    return [
        {
            "branch_id": str(b.pk),
            "branch_name": b.name,
            "code": b.code,
            "city": b.city,
            "is_active": b.is_active,
            "created_at": b.created_at.isoformat(),
        }
        for b in list_branches(tenant.pk)
    ]


def _resolve_rows(report_type, branch, params) -> list[dict]:
    """Request-time snapshot of the report rows (F-064), via module query layers.

    Only used for aggregation-style reports (grouped/annotated queries producing
    pivot-shaped rows, not one row per model instance) — those don't fit the
    ExportDefinition ABC's get_queryset()/get_row(instance) contract. Report types
    backed by a plain queryset (e.g. FEE_LEDGER, FEE_DEFAULTERS) are registered in
    the unified framework instead and never reach this function.
    """
    if report_type == ReportType.ADMISSION_FUNNEL:
        f = funnel_counts(branch.pk)
        return [{"dimension": k, **{"k": kk, "n": vv}} for k, d in f.items() for kk, vv in d.items()]
    if report_type == ReportType.HR_LEAVE_SUMMARY:
        return leave_summary(branch.pk)["rows"]
    if report_type == ReportType.ATTENDANCE_MONTHLY:
        year = int(params.get("year", timezone.now().year))
        month = int(params.get("month", timezone.now().month))
        return att_report.monthly_report(
            branch, year=year, month=month, batch_id=params.get("batchId"),
        )["rows"]
    if report_type == ReportType.ATTENDANCE_SHORTAGE:
        threshold = params.get("threshold")
        return att_report.shortage_report(
            branch,
            threshold=int(threshold) if threshold else None,
            batch_id=params.get("batchId"),
            date_from=_parse_date(params.get("fromDate"), None),
            date_to=_parse_date(params.get("toDate"), None),
        )["rows"]
    if report_type == ReportType.ATTENDANCE_DETENTION:
        return att_report.detention_report(
            branch,
            batch_id=params.get("batchId"),
            date_from=_parse_date(params.get("fromDate"), None),
            date_to=_parse_date(params.get("toDate"), None),
        )["rows"]
    if report_type == ReportType.ATTENDANCE_RANKING:
        today = timezone.localdate()
        date_from = _parse_date(params.get("fromDate"), today.replace(day=1))
        date_to = _parse_date(params.get("toDate"), today)
        return att_report.ranking_report(
            branch, date_from=date_from, date_to=date_to, batch_id=params.get("batchId"),
        )["rows"]
    return []


def _get_registered_definition(report_type):
    """Return the ExportDefinition for report_type if registered in the unified
    framework, else None (legacy report types still go through _resolve_rows)."""
    try:
        from apps.core.exports.registry import get_definition
        return get_definition(report_type)
    except (ImportError, ValueError):
        return None


def generate_report(*, tenant, branch, report_type, params=None, requester=None,
                    threshold=DEFAULT_THRESHOLD):
    """Create a ReportExport. Small → inline ready; large → queued Celery job.

    Report types registered in the ExportDefinition framework (apps/core/exports)
    delegate entirely to request_export(), which counts rows without materializing
    them and streams large exports instead of building an in-memory JSON snapshot.
    """
    params = params or {}

    if report_type == ReportType.BRANCH_SUMMARY:
        rows = _branch_summary_rows(tenant)
        export = report_q.create_export(
            tenant=tenant, branch=None, report_type=report_type, params=params,
            requested_by=requester,
        )
        report_q.update_export(export, {
            "snapshot": {"rows": rows},
            "row_count": len(rows),
            "status": ReportStatus.READY,
            "expires_at": timezone.now() + timezone.timedelta(hours=24),
        }, user=requester)
        export.refresh_from_db()
        return export

    definition = _get_registered_definition(report_type)
    if definition is not None:
        from apps.core.exports.runner import request_export
        return request_export(
            definition, tenant=tenant, branch=branch, params=params, requested_by=requester,
        )

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
