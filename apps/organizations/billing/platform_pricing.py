"""Platform SaaS pricing — annual fee per enrolled student (INR)."""

from apps.organizations.enums import BillingStatus, PlanType

# F-020 — list price per student per academic year (INR)
ANNUAL_PER_STUDENT_INR: dict[str, int] = {
    PlanType.STARTER: 600,
    PlanType.GROWTH: 500,
    PlanType.ENTERPRISE: 400,
}


def annual_subscription_inr(*, plan: str, student_count: int) -> int:
    rate = ANNUAL_PER_STUDENT_INR.get(plan, ANNUAL_PER_STUDENT_INR[PlanType.STARTER])
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
