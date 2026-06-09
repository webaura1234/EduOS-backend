"""
Queries — platform-owner tenant management (list / get / create / status).

All DB access for the platform tenant screens lives here. Frontend status
(active | inactive | pending) is mapped to/from the richer model lifecycle.
"""

from django.db.models import Q
from django.utils import timezone

from apps.organizations.models import Branch, PlanSubscription, Tenant, TenantSettings

# Map model lifecycle → the 3-state status the platform UI uses.
_MODEL_TO_UI_STATUS = {
    "active": "active",
    "trial": "pending",
    "suspended": "inactive",
    "deactivated": "inactive",
    "offboarding": "inactive",
}
# Reverse, for filtering.
_UI_TO_MODEL_STATUSES = {
    "active": ["active"],
    "pending": ["trial"],
    "inactive": ["suspended", "deactivated", "offboarding"],
}


def to_ui_status(model_status: str) -> str:
    return _MODEL_TO_UI_STATUS.get(model_status, "inactive")


def list_tenants(*, q=None, plan="all", institution_type="all", city="all", status="all"):
    """Filtered tenant queryset (newest first), with subscription pre-joined."""
    qs = Tenant.objects.select_related("subscription").order_by("-created_at")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(subdomain__icontains=q))
    if institution_type and institution_type != "all":
        qs = qs.filter(institution_type=institution_type)
    if city and city != "all":
        qs = qs.filter(city__iexact=city)
    if plan and plan != "all":
        qs = qs.filter(subscription__plan=plan)
    if status and status != "all":
        qs = qs.filter(status__in=_UI_TO_MODEL_STATUSES.get(status, []))
    return qs


def get_tenant(tenant_id) -> Tenant | None:
    try:
        return Tenant.objects.select_related("subscription").get(pk=tenant_id)
    except (Tenant.DoesNotExist, ValueError, TypeError):
        return None


def branch_count(tenant_id) -> int:
    return Branch.objects.filter(tenant_id=tenant_id).count()


def distinct_cities() -> list[str]:
    return sorted(c for c in Tenant.objects.values_list("city", flat=True).distinct() if c)


def status_counts() -> dict:
    """Aggregate counts keyed by UI status for the list-screen stat cards."""
    counts = {"total": 0, "active": 0, "inactive": 0, "pending": 0}
    for model_status in Tenant.objects.values_list("status", flat=True):
        counts["total"] += 1
        ui = to_ui_status(model_status)
        counts[ui] = counts.get(ui, 0) + 1
    return counts


# ── Writes (called within a transaction by the interactor) ────────────────────

def create_tenant(*, name, subdomain, institution_type, city, state,
                  address_line1="", address_line2="", postal_code="",
                  parent_access_enabled, settings_json) -> Tenant:
    return Tenant.objects.create(
        name=name,
        subdomain=subdomain.strip().lower(),
        institution_type=institution_type,
        city=city,
        state=state,
        address_line1=address_line1,
        address_line2=address_line2,
        postal_code=postal_code,
        parent_access_enabled=parent_access_enabled,
        settings=settings_json,
        status="trial",
    )


def create_settings(tenant) -> TenantSettings:
    return TenantSettings.objects.create(tenant=tenant)


def create_subscription(tenant, plan, limits: dict) -> PlanSubscription:
    return PlanSubscription.objects.create(tenant=tenant, plan=plan, **limits)


def create_primary_branch(tenant, name, city, state) -> Branch:
    return Branch.objects.create(
        tenant=tenant, name=name, city=city, state=state, is_primary=True
    )


def set_status(tenant: Tenant, *, model_status: str) -> Tenant:
    now = timezone.now()
    tenant.status = model_status
    if model_status == "active":
        tenant.activated_at = tenant.activated_at or now
        tenant.deactivated_at = None
    elif model_status == "deactivated":
        tenant.deactivated_at = now
    tenant.save(update_fields=["status", "activated_at", "deactivated_at"])
    return tenant
