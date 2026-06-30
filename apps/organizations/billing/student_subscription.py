"""Create and backfill per-student platform subscription rows."""

from __future__ import annotations

import datetime

from django.db.models import Q, Sum
from django.utils import timezone

from apps.accounts.models.user import Role, User
from apps.fees.helpers.paise import financial_year_for
from apps.organizations.billing.platform_pricing import ANNUAL_PER_STUDENT_INR
from apps.organizations.enums import BillingStatus, StudentPlatformSubscriptionStatus
from apps.organizations.models import PlanSubscription, StudentPlatformSubscription


def current_academic_year(*, on_date: datetime.date | None = None) -> str:
    return financial_year_for(on_date or timezone.localdate())


def _default_status_for_tenant(tenant_id) -> str:
    try:
        sub = PlanSubscription.objects.get(tenant_id=tenant_id)
        if sub.billing_status == BillingStatus.PAID:
            return StudentPlatformSubscriptionStatus.PAID
    except PlanSubscription.DoesNotExist:
        pass
    return StudentPlatformSubscriptionStatus.UNPAID


def annual_fee_for_plan(plan: str) -> int:
    return ANNUAL_PER_STUDENT_INR.get(plan, ANNUAL_PER_STUDENT_INR["starter"])


def upsert_student_platform_subscription(
    *,
    student_user: User,
    academic_year: str | None = None,
    status: str | None = None,
) -> StudentPlatformSubscription:
    """Ensure a subscription row exists for an active student user."""
    if student_user.role != Role.STUDENT:
        raise ValueError("Platform subscriptions apply to student users only.")
    if not student_user.tenant_id or not student_user.branch_id:
        raise ValueError("Student must belong to a tenant and branch.")

    year = academic_year or current_academic_year()
    try:
        plan_sub = PlanSubscription.objects.get(tenant_id=student_user.tenant_id)
        plan = plan_sub.plan
    except PlanSubscription.DoesNotExist:
        plan = "starter"

    fee = annual_fee_for_plan(plan)
    resolved_status = status or _default_status_for_tenant(student_user.tenant_id)
    paid_at = timezone.now() if resolved_status == StudentPlatformSubscriptionStatus.PAID else None

    row, created = StudentPlatformSubscription.objects.get_or_create(
        student_user_id=student_user.id,
        academic_year=year,
        defaults={
            "tenant_id": student_user.tenant_id,
            "branch_id": student_user.branch_id,
            "plan": plan,
            "annual_fee_inr": fee,
            "status": resolved_status,
            "paid_at": paid_at,
        },
    )
    if not created:
        updates: list[str] = []
        if row.branch_id != student_user.branch_id:
            row.branch_id = student_user.branch_id
            updates.append("branch_id")
        if row.plan != plan:
            row.plan = plan
            row.annual_fee_inr = fee
            updates.extend(["plan", "annual_fee_inr"])
        if updates:
            row.save(update_fields=updates + ["updated_at"])
    return row


def backfill_student_platform_subscriptions(
    *,
    tenant_id=None,
    academic_year: str | None = None,
    paid_fraction: float = 0.6,
) -> int:
    """
    Create subscription rows for all active students missing a row this year.
    Marks ~paid_fraction as paid for demo data.
    """
    year = academic_year or current_academic_year()
    qs = User.objects.filter(role=Role.STUDENT, is_active=True, tenant__isnull=False)
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)

    existing = set(
        StudentPlatformSubscription.objects.filter(academic_year=year).values_list(
            "student_user_id", flat=True
        )
    )

    created = 0
    students = list(qs.select_related("tenant"))
    for idx, student in enumerate(students):
        if student.id in existing:
            continue
        if paid_fraction >= 1.0:
            status = StudentPlatformSubscriptionStatus.PAID
        elif paid_fraction <= 0.0:
            status = StudentPlatformSubscriptionStatus.UNPAID
        else:
            status = (
                StudentPlatformSubscriptionStatus.PAID
                if (idx % 10) < int(paid_fraction * 10)
                else StudentPlatformSubscriptionStatus.UNPAID
            )
        upsert_student_platform_subscription(
            student_user=student,
            academic_year=year,
            status=status,
        )
        created += 1
    return created


def aggregate_platform_subscription_stats(*, tenant_id=None) -> dict:
    """Global or tenant-scoped stats from per-student subscription rows."""
    year = current_academic_year()
    qs = StudentPlatformSubscription.objects.filter(academic_year=year, is_active=True)
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)

    total = qs.count()
    paid = qs.filter(status=StudentPlatformSubscriptionStatus.PAID).count()
    unpaid = qs.filter(status=StudentPlatformSubscriptionStatus.UNPAID).count()
    overdue = qs.filter(status=StudentPlatformSubscriptionStatus.OVERDUE).count()

    sums = qs.aggregate(
        annual=Sum("annual_fee_inr"),
        collected=Sum(
            "annual_fee_inr",
            filter=Q(status=StudentPlatformSubscriptionStatus.PAID),
        ),
    )

    return {
        "totalStudents": total,
        "paid": paid,
        "unpaid": unpaid,
        "overdue": overdue,
        "annualSubscriptionInr": int(sums["annual"] or 0),
        "collectedSubscriptionInr": int(sums["collected"] or 0),
    }
