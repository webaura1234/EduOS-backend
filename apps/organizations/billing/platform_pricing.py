"""Platform SaaS pricing — annual fee per enrolled student (INR).

Thin wrappers over the unified pricing service. Prices are plan-aware and
apply per-tenant discounts; the pricing source of truth is
``apps.organizations.billing.pricing``.
"""

from apps.organizations.billing import pricing
from apps.organizations.enums import BillingStatus

# Licensing list price fallback (INR) — used only when no plan definition exists.
DEFAULT_LICENSE_PRICE_INR = 499


def unit_price_for_tenant(tenant_id, plan: str | None = None) -> int:
    """Net per-student price for a tenant (plan list price minus tenant discount)."""
    return pricing.net_unit_price_inr(tenant_id, plan)


def annual_subscription_inr(*, plan: str, student_count: int, tenant_id=None) -> int:
    """Annual subscription = students x net per-student price.

    When ``tenant_id`` is provided the tenant discount is applied; otherwise the
    plan list price is used.
    """
    if tenant_id is not None:
        rate = pricing.net_unit_price_inr(tenant_id, plan)
    else:
        rate = pricing.list_price_for_plan(plan)
    return max(0, int(student_count)) * rate


def collected_subscription_inr(*, billing_status: str, annual_inr: int) -> int:
    """Collected = full annual amount only when tenant subscription is marked paid."""
    if billing_status == BillingStatus.PAID:
        return annual_inr
    return 0


def amount_due_inr(*, billing_status: str, annual_inr: int) -> int:
    if billing_status in (BillingStatus.TRIAL, BillingStatus.OVERDUE):
        return annual_inr
    return 0
