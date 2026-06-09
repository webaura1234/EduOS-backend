"""
Queries — PlanSubscription and TenantQuota reads for the plan screen.
"""

from apps.organizations.models import PlanSubscription, TenantQuota


def get_subscription(tenant_id) -> PlanSubscription | None:
    try:
        return PlanSubscription.objects.get(tenant_id=tenant_id)
    except PlanSubscription.DoesNotExist:
        return None


def list_quotas(tenant_id) -> list[TenantQuota]:
    return list(TenantQuota.objects.filter(tenant_id=tenant_id))
