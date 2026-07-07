"""Plan-level gate for AI features — Standard ERP tenants cannot use AI."""

from apps.organizations.models import PlanSubscription
from apps.organizations.plan_catalog import PLAN_LIMITS, normalize_plan


class AiAccessDenied(PermissionError):
    """Raised when AI is not available on the tenant's plan."""


def tenant_has_ai_plan(tenant_id) -> bool:
    try:
        sub = PlanSubscription.objects.get(tenant_id=tenant_id)
    except PlanSubscription.DoesNotExist:
        return False
    plan = normalize_plan(sub.plan)
    return bool(PLAN_LIMITS.get(plan, {}).get("includesAi"))


def require_ai_plan(tenant_id) -> None:
    if not tenant_has_ai_plan(tenant_id):
        raise AiAccessDenied(
            "AI features require the AI ERP plan. Upgrade from Standard ERP to enable AI."
        )
