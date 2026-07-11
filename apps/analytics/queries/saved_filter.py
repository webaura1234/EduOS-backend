"""Queries — saved report filter presets."""

from apps.analytics.models import SavedReportFilter


def list_saved_filters(tenant_id, user_id, report_type=None):
    qs = SavedReportFilter.objects.filter(
        tenant_id=tenant_id, user_id=user_id, is_active=True,
    )
    if report_type:
        qs = qs.filter(report_type=report_type)
    return qs.order_by("name")


def create_saved_filter(*, tenant, user, report_type, name, params) -> SavedReportFilter:
    return SavedReportFilter.objects.create(
        tenant=tenant,
        user=user,
        report_type=report_type,
        name=name,
        params=params or {},
        created_by=user,
        updated_by=user,
    )


def delete_saved_filter(tenant_id, user_id, filter_id) -> bool:
    updated = SavedReportFilter.objects.filter(
        pk=filter_id, tenant_id=tenant_id, user_id=user_id, is_active=True,
    ).update(is_active=False)
    return updated > 0
