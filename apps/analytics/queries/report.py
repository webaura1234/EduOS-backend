"""Queries — ReportExport (all ORM here)."""

from apps.analytics.models import ReportExport


def create_export(*, tenant, branch, report_type, params, requested_by=None) -> ReportExport:
    return ReportExport.objects.create(
        tenant=tenant, branch=branch, report_type=report_type, params=params or {},
        requested_by=requested_by, created_by=requested_by, updated_by=requested_by,
    )


def get_export(tenant_id, export_id) -> ReportExport | None:
    try:
        return ReportExport.objects.get(tenant_id=tenant_id, pk=export_id, is_active=True)
    except (ReportExport.DoesNotExist, ValueError, TypeError):
        return None


def get_export_by_id(export_id) -> ReportExport | None:
    try:
        return ReportExport.objects.get(pk=export_id)
    except (ReportExport.DoesNotExist, ValueError, TypeError):
        return None


def update_export(export: ReportExport, fields: dict, user=None) -> ReportExport:
    for k, v in fields.items():
        setattr(export, k, v)
    if user:
        export.updated_by = user
    export.save(update_fields=list(fields.keys()) + (["updated_by"] if user else []) + ["updated_at"])
    return export


def list_exports(tenant_id):
    return ReportExport.objects.filter(tenant_id=tenant_id, is_active=True).order_by("-created_at")
