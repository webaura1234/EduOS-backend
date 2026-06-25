"""Celery tasks — large report exports (OD-2).

Serializes the report's request-time snapshot to CSV and uploads it via the S3 adapter
(sandbox in tests/dev, live at deploy). Runs eagerly in tests (CELERY_TASK_ALWAYS_EAGER).
"""

import csv
import io

from celery import shared_task

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
    return buf.getvalue().encode("utf-8")


def rows_to_csv_bytes(rows: list[dict]) -> bytes:
    """Public helper for views and Celery tasks."""
    return _rows_to_csv(rows)


@shared_task
def generate_export_task(export_id):
    """Build a CSV from the frozen snapshot and upload it to S3; set the signed URL."""
    export = report_q.get_export_by_id(export_id)
    if export is None:
        return
    report_q.update_export(export, {"status": ReportStatus.RUNNING})
    try:
        rows = (export.snapshot or {}).get("rows", [])
        content = rows_to_csv_bytes(rows)
        s3 = get_s3_adapter()
        key = f"exports/{export.tenant_id}/{export.pk}.csv"
        s3.upload(key=key, content=content, content_type="text/csv")
        url = s3.signed_url(key=key)
        report_q.update_export(export, {
            "status": ReportStatus.READY, "file_key": key, "download_url": url,
        })
    except Exception as exc:  # noqa: BLE001 — record failure, no partial state
        report_q.update_export(export, {"status": ReportStatus.FAILED, "error": str(exc)})
        raise
