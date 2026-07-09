"""
Queries — platform-owner tenant management (list / get / create / status / plans).

All DB access for the platform tenant screens lives here. Frontend status
(active | inactive | pending) is mapped to/from the richer model lifecycle.
"""

from django.db.models import Q
from django.utils import timezone

from apps.accounts.models.user import Role
from apps.accounts.queries.user import count_active_by_role_in_tenant
from apps.organizations.models import Branch, PlanSubscription, Tenant, TenantSettings
from apps.organizations.plan_catalog import PLAN_LIMITS, PLAN_ORDER, normalize_plan

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
                  parent_access_enabled, settings_json, user=None) -> Tenant:
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
        created_by=user,
        updated_by=user,
    )


def create_settings(tenant, user=None) -> TenantSettings:
    return TenantSettings.objects.create(tenant=tenant, created_by=user, updated_by=user)


def create_subscription(tenant, plan, limits: dict, user=None) -> PlanSubscription:
    return PlanSubscription.objects.create(
        tenant=tenant, plan=plan, created_by=user, updated_by=user, **limits
    )


def create_primary_branch(tenant, name, city, state, user=None) -> Branch:
    return Branch.objects.create(
        tenant=tenant,
        name=name,
        city=city,
        state=state,
        is_primary=True,
        created_by=user,
        updated_by=user,
    )


def plan_catalog() -> list[dict]:
    """Return the DB-backed plan catalog for the frontend PlatformPlanLimits[] type."""
    from apps.organizations.billing import pricing

    return pricing.plan_catalog_for_api()


def plan_rows() -> list[dict]:
    """Return PlatformTenantPlanRow dicts for every tenant."""
    tenants = Tenant.objects.select_related("subscription").order_by("name")
    rows = []
    for tenant in tenants:
        subscription = getattr(tenant, "subscription", None)
        raw_plan = subscription.plan if subscription else "standard"
        current_plan = normalize_plan(raw_plan)
        b_count = branch_count(tenant.id)
        s_count = count_active_by_role_in_tenant(tenant.id, Role.STUDENT)
        rows.append({
            "tenantId": str(tenant.id),
            "tenantName": tenant.name,
            "subdomain": tenant.subdomain,
            "status": to_ui_status(tenant.status),
            "currentPlan": current_plan,
            "branchCount": b_count,
            "studentCount": s_count,
            "restrictedFeatures": [],
            "overBranchLimit": False,
            "overStudentLimit": False,
        })
    return rows


def validate_plan_limits(tenant_id, new_plan: str) -> dict | None:
    """
    Core ERP has no branch/student caps. Plan changes are always allowed
    between Standard and AI ERP tiers.
    """
    return None


def change_plan(tenant_id, new_plan: str, user=None) -> tuple[dict, str]:
    """
    Change a tenant's subscription plan.
    Returns (PlatformChangePlanResult dict, previous_plan).
    Raises ValueError if the tenant is not found.
  """
    from apps.organizations.serializers.platform_tenant import tenant_summary

    tenant = get_tenant(tenant_id)
    if tenant is None:
        raise ValueError("Tenant not found.")

    subscription = getattr(tenant, "subscription", None)
    if subscription is None:
        raise ValueError("Tenant has no subscription record.")

    new_plan = normalize_plan(new_plan)
    previous_plan = normalize_plan(subscription.plan)
    if previous_plan == new_plan:
        raise ValueError("Tenant is already on this plan.")

    subscription.plan = new_plan
    if user is not None:
        subscription.updated_by = user
    subscription.save(update_fields=["plan", "updated_at", "updated_by"])

    from apps.organizations.billing.billing_refresh import refresh_tenant_billing

    refresh_tenant_billing(tenant_id, user=user)

    prev_rank = PLAN_ORDER.index(previous_plan) if previous_plan in PLAN_ORDER else 0
    new_rank = PLAN_ORDER.index(new_plan) if new_plan in PLAN_ORDER else 0
    is_downgrade = new_rank < prev_rank

    restricted: list[str] = []
    if is_downgrade and PLAN_LIMITS.get(previous_plan, {}).get("includesAi"):
        restricted = ["AI features"]

    message = f"Plan updated to {PLAN_LIMITS.get(new_plan, {}).get('label', new_plan)}."
    if is_downgrade and restricted:
        message += f" Restricted: {', '.join(restricted)}."

    tenant.refresh_from_db(fields=["subscription"])
    return {
        "tenant": tenant_summary(tenant),
        "previousPlan": previous_plan,
        "newPlan": new_plan,
        "restrictedFeatures": restricted,
        "message": message,
    }


class _PlanLimitViolation(Exception):
    """Internal exception carrying a PlatformPlanLimitBlockedResponse dict."""
    def __init__(self, payload: dict):
        super().__init__("Plan limit violated")
        self.payload = payload


def set_status(tenant: Tenant, *, model_status: str, user=None) -> Tenant:
    now = timezone.now()
    tenant.status = model_status
    if model_status == "active":
        tenant.activated_at = tenant.activated_at or now
        tenant.deactivated_at = None
    elif model_status == "deactivated":
        tenant.deactivated_at = now
    if user is not None:
        tenant.updated_by = user
    tenant.save(update_fields=["status", "activated_at", "deactivated_at", "updated_by"])
    return tenant
