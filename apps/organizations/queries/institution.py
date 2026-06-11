"""
Queries — Institution (Tenant) reads/writes for the settings screen, plus
subdomain availability. All DB access for these flows lives here.
"""

from django.utils import timezone

from apps.organizations.models import Tenant, TenantSettings


def get_tenant(tenant_id) -> Tenant | None:
    try:
        return Tenant.objects.get(pk=tenant_id)
    except (Tenant.DoesNotExist, ValueError, TypeError):
        return None


def update_tenant_fields(tenant: Tenant, fields: dict) -> Tenant:
    """Persist a whitelisted set of Tenant fields and return the instance."""
    for key, value in fields.items():
        setattr(tenant, key, value)
    if fields:
        tenant.save(update_fields=list(fields.keys()))
    return tenant


def set_go_live(tenant: Tenant, live: bool) -> Tenant:
    """Mark an institution live (status active + activated_at) or undo it."""
    if live:
        tenant.status = "active"
        tenant.activated_at = tenant.activated_at or timezone.now()
        tenant.save(update_fields=["status", "activated_at"])
    else:
        tenant.status = "trial"
        tenant.activated_at = None
        tenant.save(update_fields=["status", "activated_at"])
    return tenant


def get_or_create_tenant_settings(tenant) -> TenantSettings:
    settings, _ = TenantSettings.objects.get_or_create(tenant=tenant)
    return settings


def update_tenant_settings(settings: TenantSettings, fields: dict) -> TenantSettings:
    for k, v in fields.items():
        setattr(settings, k, v)
    if fields:
        settings.save(update_fields=list(fields.keys()))
    return settings


def subdomain_taken(subdomain: str, exclude_tenant_id=None) -> bool:
    """True if the subdomain is already in use (optionally excluding one tenant)."""
    qs = Tenant.objects.filter(subdomain__iexact=subdomain.strip())
    if exclude_tenant_id is not None:
        qs = qs.exclude(pk=exclude_tenant_id)
    return qs.exists()
