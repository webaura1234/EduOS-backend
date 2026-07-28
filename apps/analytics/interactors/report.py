"""Interactors — report generation with snapshot-at-request + small/large execution.

Small reports resolve inline (frozen snapshot, F-064); large ones dispatch a Celery task
that serializes to CSV and uploads to S3 (OD-2).
"""

from apps.analytics.enums import ReportStatus, ReportType
from apps.analytics.queries import report as report_q
from apps.core.exports.registry import get_definition
from apps.core.exports.retention import export_expires_at

DEFAULT_THRESHOLD = 500
_RETRYABLE = {ReportStatus.FAILED, ReportStatus.TIMED_OUT, ReportStatus.EXPIRED}


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


def _get_registered_definition(report_type):
    try:
        return get_definition(report_type)
    except (ImportError, ValueError):
        return None


def generate_report(*, tenant, branch, report_type, params=None, requester=None,
                    threshold=DEFAULT_THRESHOLD):
    """Create a ReportExport. Small → inline ready; large → queued Celery job."""
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
            "expires_at": export_expires_at(),
            "module": "organizations",
            "title": "Branch Summary",
        }, user=requester)
        export.refresh_from_db()
        return export

    definition = _get_registered_definition(report_type)
    if definition is not None:
        from apps.core.exports.runner import request_export
        override = threshold if threshold != DEFAULT_THRESHOLD else None
        return request_export(
            definition, tenant=tenant, branch=branch, params=params, requested_by=requester,
            sync_threshold_override=override,
        )

    raise ValueError(f"No export definition registered for report_type={report_type!r}")


def retry_export(*, export, requester):
    """Re-dispatch a FAILED / TIMED_OUT / EXPIRED export with the same params."""
    if export.status not in _RETRYABLE:
        raise ValueError("Only failed, timed-out, or expired exports can be retried.")

    snapshot = dict(export.snapshot or {})
    snapshot.pop("rows", None)

    report_q.update_export(export, {
        "status": ReportStatus.QUEUED,
        "error": "",
        "file_key": "",
        "download_url": "",
        "expires_at": None,
        "snapshot": snapshot,
        "celery_task_id": "",
        "row_count": 0,
    }, user=requester)

    from apps.analytics.tasks import generate_export_task
    generate_export_task.delay(str(export.pk))
    export.refresh_from_db()
    return export


def naac_export(*, tenant, branch) -> dict:
    """F-048 / F-237 — accreditation export that lists missing fields but still exports."""
    from apps.accounts.models.user import Role
    from apps.accounts.queries.user import count_active_by_role_in_tenant

    data = {
        "studentsCount": count_active_by_role_in_tenant(tenant.pk, Role.STUDENT),
        "facultyCount": count_active_by_role_in_tenant(tenant.pk, Role.FACULTY),
        "branchName": branch.name,
    }
    missing = ["studentTeacherRatioCriteria", "researchOutput", "infrastructureScore"]
    return {"data": data, "missingFields": missing}
