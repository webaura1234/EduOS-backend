"""
Queries — tenant lookups.

Pure database access for the organizations app. No business logic here.
"""

from apps.organizations.models import Tenant, TenantSettings

DEFAULT_STUDENT_ID_LABEL = "Roll Number"
DEFAULT_FACULTY_ID_LABEL = "Employee ID"


def get_active_tenant_by_subdomain(subdomain: str) -> Tenant | None:
    """Return an active Tenant matching the subdomain (case-insensitive), or None."""
    try:
        return Tenant.objects.get(subdomain__iexact=subdomain.strip(), status="active")
    except Tenant.DoesNotExist:
        return None


def get_tenant_id_labels(tenant: Tenant) -> tuple[str, str]:
    """
    Return (student_id_label, faculty_id_label) for a tenant, falling back to
    defaults when no TenantSettings row exists.
    """
    try:
        settings = tenant.tenant_settings
        return settings.student_id_label, settings.faculty_id_label
    except TenantSettings.DoesNotExist:
        return DEFAULT_STUDENT_ID_LABEL, DEFAULT_FACULTY_ID_LABEL
