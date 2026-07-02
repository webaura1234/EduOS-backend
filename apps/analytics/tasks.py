"""Celery tasks — large report exports (OD-2) + nightly cleanup.

Serializes the report's request-time snapshot to CSV and uploads it via the S3 adapter
(sandbox in tests/dev, live at deploy). Runs eagerly in tests (CELERY_TASK_ALWAYS_EAGER).
"""

import csv
import io

from celery import shared_task
from django.utils.timezone import now

from apps.analytics.enums import ReportStatus
from apps.analytics.queries import report as report_q
from apps.integrations.adapters.s3 import get_s3_adapter


def _rows_to_csv(rows: list[dict]) -> bytes:
    if not rows:
        return b""
    buf = io.StringIO()
    fieldnames = sorted({k for r in rows for k in r.keys()})
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility


def rows_to_csv_bytes(rows: list[dict]) -> bytes:
    """Public helper for views and Celery tasks."""
    return _rows_to_csv(rows)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_kwargs={"max_retries": 3},
)
def generate_export_task(self, export_id):
    """Build a CSV from the frozen snapshot and upload it to S3; set the signed URL."""
    export = report_q.get_export_by_id(export_id)
    if export is None:
        return
    report_q.update_export(export, {
        "status": ReportStatus.RUNNING,
        "celery_task_id": self.request.id or "",
    })
    try:
        # Check if a definition exists in the registry for streaming large exports.
        # Falls back to snapshot-based generation for legacy report types.
        definition = _try_get_definition(export.report_type)
        if definition is not None:
            content = _stream_definition_to_csv(definition, export)
        else:
            rows = (export.snapshot or {}).get("rows", [])
            content = rows_to_csv_bytes(rows)

        s3 = get_s3_adapter()
        key = f"exports/{export.tenant_id}/{export.pk}.csv"
        s3.upload(key=key, content=content, content_type="text/csv")
        url = s3.signed_url(key=key)
        from django.utils.timezone import timedelta
        report_q.update_export(export, {
            "status": ReportStatus.READY,
            "file_key": key,
            "download_url": url,
            "expires_at": now() + timedelta(hours=24),
        })
    except Exception as exc:
        if self.request.retries >= self.max_retries:
            report_q.update_export(export, {"status": ReportStatus.FAILED, "error": str(exc)})
        raise


def _try_get_definition(report_type: str):
    """Return the ExportDefinition for this report_type, or None if not registered."""
    try:
        from apps.core.exports.registry import get_definition
        return get_definition(report_type)
    except (ImportError, ValueError):
        return None


def _stream_definition_to_csv(definition, export) -> bytes:
    """Stream rows from a definition's queryset directly to CSV bytes (constant memory)."""
    qs = definition.get_queryset_for_export(
        tenant_id=export.tenant_id,
        branch_id=export.branch_id,
        params=export.params or {},
    )
    columns = definition.get_columns(export.params or {})
    buf = io.StringIO()
    csv.writer(buf).writerow([c.label for c in columns])  # friendly header row
    writer = csv.DictWriter(buf, fieldnames=[c.key for c in columns], extrasaction="ignore")
    for obj in qs.iterator(chunk_size=2000):
        writer.writerow(definition.get_row(obj))
    return buf.getvalue().encode("utf-8-sig")


@shared_task
def purge_expired_exports():
    """Nightly cleanup: delete expired ReportExport records and their S3 objects."""
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
            except Exception:  # noqa: BLE001 — best-effort, don't block row deletion
                pass
    expired.delete()
