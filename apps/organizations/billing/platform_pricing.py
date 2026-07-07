"""Platform SaaS pricing — annual fee per enrolled student (INR)."""

from apps.organizations.enums import BillingStatus, PlanType
from apps.organizations.plan_catalog import PLAN_PRICE_PER_STUDENT_INR, normalize_plan

# Licensing list price — one student license per academic year (INR).
# Configurable per tenant via TenantLicensePricing; this is the default.
DEFAULT_LICENSE_PRICE_INR = 499

# Per-plan seat price for the student subscription roster.
ANNUAL_PER_STUDENT_INR: dict[str, int] = PLAN_PRICE_PER_STUDENT_INR


def unit_price_for_tenant(tenant_id) -> int:
    """License unit price for a tenant — per-tenant override, else list price."""
    from apps.organizations.models import TenantLicensePricing

    row = TenantLicensePricing.objects.filter(tenant_id=tenant_id, is_active=True).first()
    return row.price_per_student_inr if row else DEFAULT_LICENSE_PRICE_INR


def annual_subscription_inr(*, plan: str, student_count: int) -> int:
    plan = normalize_plan(plan)
    rate = ANNUAL_PER_STUDENT_INR.get(plan, ANNUAL_PER_STUDENT_INR[PlanType.STANDARD])
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
