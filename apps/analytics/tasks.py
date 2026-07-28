"""Celery tasks — large report exports (OD-2) + nightly soft-expire cleanup."""

from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.utils.timezone import now

from apps.analytics.enums import ReportStatus
from apps.analytics.queries import report as report_q
from apps.core.exports.base import AggregationExportDefinition
from apps.core.exports.csv import queryset_to_csv_bytes, rows_to_csv_bytes as csv_rows_to_bytes
from apps.core.exports.retention import export_expires_at
from apps.integrations.adapters.s3 import get_s3_adapter

# Soft wall-clock budget for heavy aggregations (plan 5.2).
_EXPORT_SOFT_TIME_LIMIT = 120
_EXPORT_HARD_TIME_LIMIT = 150


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 3},
    soft_time_limit=_EXPORT_SOFT_TIME_LIMIT,
    time_limit=_EXPORT_HARD_TIME_LIMIT,
)
def generate_export_task(self, export_id):
    """Build a CSV from the frozen snapshot or stream definition queryset; upload to S3."""
    export = report_q.get_export_by_id(export_id)
    if export is None:
        return
    report_q.update_export(export, {
        "status": ReportStatus.RUNNING,
        "celery_task_id": self.request.id or "",
    })
    try:
        definition = _try_get_definition(export.report_type)
        params = export.params or {}

        if definition is not None and isinstance(definition, AggregationExportDefinition):
            rows = (export.snapshot or {}).get("rows")
            if rows is None:
                from apps.organizations.models import Branch
                branch = Branch.objects.filter(pk=export.branch_id).first() if export.branch_id else None
                rows = definition.resolve_rows(tenant=export.tenant, branch=branch, params=params)
            columns = definition.get_columns(params)
            content = csv_rows_to_bytes(rows, columns)
            row_count = len(rows)
        elif definition is not None:
            qs = definition.get_queryset_for_export(
                tenant_id=export.tenant_id,
                branch_id=export.branch_id,
                params=params,
            )
            content, rows = queryset_to_csv_bytes(definition, qs, params)
            row_count = len(rows)
        else:
            rows = (export.snapshot or {}).get("rows", [])
            content = csv_rows_to_bytes(rows, None)
            row_count = len(rows)

        s3 = get_s3_adapter()
        key = f"exports/{export.tenant_id}/{export.pk}.csv"
        s3.upload(key=key, content=content, content_type="text/csv")
        url = s3.signed_url(key=key)
        report_q.update_export(export, {
            "status": ReportStatus.READY,
            "file_key": key,
            "download_url": url,
            "expires_at": export_expires_at(),
            "row_count": row_count,
            "error": "",
        })
    except SoftTimeLimitExceeded:
        report_q.update_export(export, {
            "status": ReportStatus.TIMED_OUT,
            "error": "Export exceeded the time budget. Retry or narrow filters.",
        })
        return
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            report_q.update_export(export, {"status": ReportStatus.FAILED, "error": str(exc)})
        raise


def rows_to_csv_bytes(rows: list[dict], columns=None) -> bytes:
    """Public helper for views and legacy snapshot exports."""
    return csv_rows_to_bytes(rows, columns)


def _try_get_definition(report_type: str):
    try:
        from apps.core.exports.registry import get_definition
        return get_definition(report_type)
    except (ImportError, ValueError):
        return None


@shared_task
def purge_expired_exports():
    """Nightly cleanup: soft-expire READY exports past expires_at (delete S3, keep row)."""
    from apps.analytics.models import ReportExport

    expired = ReportExport.objects.filter(
        expires_at__lt=now(),
        status=ReportStatus.READY,
        is_active=True,
    )
    s3 = get_s3_adapter()
    for export in expired.iterator():
        if export.file_key:
            try:
                s3.delete(key=export.file_key)
            except Exception:  # noqa: BLE001
                pass
        report_q.update_export(export, {
            "status": ReportStatus.EXPIRED,
            "file_key": "",
            "download_url": "",
            "error": "Report file expired — regenerate.",
        })
