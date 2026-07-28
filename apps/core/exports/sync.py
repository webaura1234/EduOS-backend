"""Log instant (sync) CSV exports to ReportExport for export history."""

from apps.analytics.enums import ReportStatus
from apps.analytics.queries import report as report_q
from apps.core.exports.csv import rows_to_csv_bytes
from apps.core.exports.registry import get_definition
from apps.core.exports.retention import export_expires_at
from apps.integrations.adapters.s3 import get_s3_adapter


def log_instant_csv_export(
    *,
    tenant,
    branch,
    report_type: str,
    params: dict,
    requested_by,
    rows: list[dict] | None = None,
    csv_bytes: bytes | None = None,
    module: str = "",
    title: str = "",
) -> object | None:
    """Create a READY ReportExport row and upload CSV — for legacy sync download paths.

    When ``csv_bytes`` is supplied, those exact bytes are uploaded (preserves legacy CSV
    structure including dynamic columns). ``rows`` is used for row_count/snapshot; if
    omitted, rows are parsed from ``csv_bytes``.
    """
    try:
        definition = get_definition(report_type)
        columns = definition.get_columns(params)
        module = module or getattr(definition, "module", "")
        title = title or getattr(definition, "title", report_type)
    except ValueError:
        columns = None

    if rows is None and csv_bytes is not None:
        import csv
        import io
        text = csv_bytes.decode("utf-8-sig")
        rows = list(csv.DictReader(io.StringIO(text)))

    rows = rows or []

    if csv_bytes is None:
        csv_bytes = rows_to_csv_bytes(rows, columns)

    export = report_q.create_export(
        tenant=tenant,
        branch=branch,
        report_type=report_type,
        params=params or {},
        requested_by=requested_by,
    )
    s3 = get_s3_adapter()
    key = f"exports/{tenant.pk}/{export.pk}.csv"
    s3.upload(key=key, content=csv_bytes, content_type="text/csv")
    url = s3.signed_url(key=key)
    report_q.update_export(export, {
        "row_count": len(rows),
        "format": "csv",
        "module": module,
        "title": title,
        "status": ReportStatus.READY,
        "snapshot": {"rows": rows},
        "file_key": key,
        "download_url": url,
        "expires_at": export_expires_at(),
    }, user=requested_by)
    export.refresh_from_db()
    return export
