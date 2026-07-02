"""Unified export runner — sync/async routing for all export types.

Entry point: call request_export(). It counts rows, decides sync vs async,
creates a ReportExport record, and either fills it inline or dispatches a Celery task.
"""

import csv
import io

from django.utils.timezone import now, timedelta
from rest_framework.exceptions import PermissionDenied

from apps.analytics.enums import ReportStatus
from apps.analytics.queries import report as report_q
from apps.core.exports.base import ExportDefinition


def request_export(
    definition: ExportDefinition,
    *,
    tenant,
    branch,
    params: dict,
    requested_by,
) -> object:
    """Create a ReportExport record and either resolve it inline or enqueue a Celery task."""
    if definition.allowed_roles and getattr(requested_by, "role", None) not in definition.allowed_roles:
        raise PermissionDenied(f"Role '{getattr(requested_by, 'role', None)}' cannot request this report.")

    qs = definition.get_queryset_for_export(
        tenant_id=tenant.pk,
        branch_id=branch.pk if branch else None,
        params=params,
    )
    count = qs.count()

    export = report_q.create_export(
        tenant=tenant,
        branch=branch,
        report_type=definition.report_type,
        params=params,
        requested_by=requested_by,
    )
    report_q.update_export(
        export, {"row_count": count, "format": definition.formats[0]}, user=requested_by
    )

    if count <= definition.sync_threshold:
        _generate_inline(export, definition, qs, requested_by)
    else:
        report_q.update_export(export, {"status": ReportStatus.QUEUED}, user=requested_by)
        from apps.analytics.tasks import generate_export_task
        generate_export_task.delay(str(export.pk))

    export.refresh_from_db()
    return export


def _generate_inline(export, definition: ExportDefinition, qs, user=None) -> None:
    columns = definition.get_columns(export.params or {})
    buf = io.StringIO()
    csv.writer(buf).writerow([c.label for c in columns])  # friendly header row
    writer = csv.DictWriter(buf, fieldnames=[c.key for c in columns], extrasaction="ignore")
    rows_dicts = []
    for obj in qs.iterator(chunk_size=500):
        row = definition.get_row(obj)
        rows_dicts.append(row)
        writer.writerow(row)

    csv_bytes = buf.getvalue().encode("utf-8-sig")

    from apps.integrations.adapters.s3 import get_s3_adapter
    s3 = get_s3_adapter()
    key = f"exports/{export.tenant_id}/{export.pk}.csv"
    s3.upload(key=key, content=csv_bytes, content_type="text/csv")
    url = s3.signed_url(key=key)

    report_q.update_export(export, {
        "status": ReportStatus.READY,
        "snapshot": {"rows": rows_dicts},
        "file_key": key,
        "download_url": url,
        "expires_at": now() + timedelta(hours=24),
    }, user=user)
