"""Unified export runner — sync/async routing for all export types.

Entry point: call request_export(). It counts rows, decides sync vs async,
creates a ReportExport record, and either fills it inline or dispatches a Celery task.
"""

from django.utils.timezone import now, timedelta
from rest_framework.exceptions import PermissionDenied

from apps.analytics.enums import ReportStatus
from apps.analytics.queries import report as report_q
from apps.core.exports.base import AggregationExportDefinition, ExportDefinition
from apps.core.exports.csv import queryset_to_csv_bytes, rows_to_csv_bytes
from apps.core.exports.params import validate_params


def request_export(
    definition: ExportDefinition,
    *,
    tenant,
    branch,
    params: dict,
    requested_by,
    sync_threshold_override: int | None = None,
) -> object:
    """Create a ReportExport record and either resolve it inline or enqueue a Celery task."""
    if definition.allowed_roles and getattr(requested_by, "role", None) not in definition.allowed_roles:
        raise PermissionDenied(f"Role '{getattr(requested_by, 'role', None)}' cannot request this report.")

    params = validate_params(definition, params)
    threshold = (
        sync_threshold_override
        if sync_threshold_override is not None
        else definition.sync_threshold
    )

    if isinstance(definition, AggregationExportDefinition):
        rows = definition.resolve_rows(tenant=tenant, branch=branch, params=params)
        count = len(rows)
        export = _create_export_record(
            definition, tenant, branch, params, requested_by, count,
        )
        if count <= threshold:
            _generate_inline_rows(export, definition, rows, requested_by)
        else:
            report_q.update_export(
                export,
                {"snapshot": {"rows": rows}, "status": ReportStatus.QUEUED},
                user=requested_by,
            )
            from apps.analytics.tasks import generate_export_task
            generate_export_task.delay(str(export.pk))
    else:
        qs = definition.get_queryset_for_export(
            tenant_id=tenant.pk,
            branch_id=branch.pk if branch else None,
            params=params,
        )
        count = qs.count()
        export = _create_export_record(
            definition, tenant, branch, params, requested_by, count,
        )
        if count <= threshold:
            _generate_inline_queryset(export, definition, qs, requested_by)
        else:
            report_q.update_export(export, {"status": ReportStatus.QUEUED}, user=requested_by)
            from apps.analytics.tasks import generate_export_task
            generate_export_task.delay(str(export.pk))

    export.refresh_from_db()
    return export


def _create_export_record(definition, tenant, branch, params, requested_by, count):
    export = report_q.create_export(
        tenant=tenant,
        branch=branch,
        report_type=definition.report_type,
        params=params,
        requested_by=requested_by,
    )
    report_q.update_export(export, {
        "row_count": count,
        "format": definition.formats[0],
        "module": definition.module or "",
        "title": definition.title or "",
    }, user=requested_by)
    return export


def _upload_csv_and_finalize(export, csv_bytes, rows_dicts, user=None) -> None:
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


def _generate_inline_queryset(export, definition, qs, user=None) -> None:
    csv_bytes, rows_dicts = queryset_to_csv_bytes(definition, qs, export.params or {})
    _upload_csv_and_finalize(export, csv_bytes, rows_dicts, user)


def _generate_inline_rows(export, definition, rows, user=None) -> None:
    columns = definition.get_columns(export.params or {})
    csv_bytes = rows_to_csv_bytes(rows, columns)
    _upload_csv_and_finalize(export, csv_bytes, rows, user)
