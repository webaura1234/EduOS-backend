"""Materialize tenant billing — net unit price, per-student fees, and summary totals."""

from __future__ import annotations

from django.db.models import Sum
from django.utils import timezone

from apps.organizations.billing import pricing
from apps.organizations.billing.student_subscription import current_academic_year
from apps.organizations.enums import StudentPlatformSubscriptionStatus
from apps.organizations.models import (
    StudentPlatformSubscription,
    Tenant,
    TenantLicensePricing,
    TenantLicenseSummary,
)
from apps.organizations.plan_catalog import normalize_plan


def refresh_tenant_billing(tenant_id, *, user=None) -> TenantLicenseSummary:
    """Recompute and persist net unit price, student fees, and summary subscription totals."""
    from apps.organizations.billing import license_allocator as alloc

    tenant = Tenant.objects.filter(pk=tenant_id, is_active=True).first()
    if tenant is None:
        raise ValueError("Tenant not found.")

    plan = pricing.plan_for_tenant(tenant_id)
    list_price = pricing.list_price_for_plan(plan)
    pricing_row, _ = TenantLicensePricing.objects.get_or_create(tenant=tenant)
    discount = pricing_row.discount_percent
    net_unit = pricing.apply_discount(list_price, discount)

    pricing_row.net_unit_price_inr = net_unit
    if user is not None:
        pricing_row.updated_by = user
    pricing_row.save(update_fields=["net_unit_price_inr", "updated_by", "updated_at"])

    year = current_academic_year()
    StudentPlatformSubscription.objects.filter(
        tenant_id=tenant_id,
        academic_year=year,
        is_active=True,
    ).update(annual_fee_inr=net_unit, plan=plan, updated_at=timezone.now())

    sub_qs = StudentPlatformSubscription.objects.filter(
        tenant_id=tenant_id,
        academic_year=year,
        is_active=True,
    )
    active_count = sub_qs.count()
    collected = int(
        sub_qs.filter(status=StudentPlatformSubscriptionStatus.PAID).aggregate(
            total=Sum("annual_fee_inr"),
        )["total"]
        or 0
    )
    annual_total = active_count * net_unit

    summary = alloc.refresh_summary(tenant)
    summary.active_student_count = active_count
    summary.annual_subscription_inr = annual_total
    summary.collected_subscription_inr = collected
    summary.pending_amount_inr = summary.unlicensed_active_count * net_unit
    summary.save(
        update_fields=[
            "active_student_count",
            "annual_subscription_inr",
            "collected_subscription_inr",
            "pending_amount_inr",
            "updated_at",
        ],
    )
    return summary


def subscription_collected_trend(*, months: int = 6, tenant_id=None) -> list[dict]:
    """Sum of paid student subscription fees grouped by calendar month (real data)."""
    import datetime

    from django.db.models import Sum

    qs = StudentPlatformSubscription.objects.filter(
        status=StudentPlatformSubscriptionStatus.PAID,
        paid_at__isnull=False,
        is_active=True,
    )
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)

    now = timezone.localtime()
    trend: list[dict] = []
    for offset in range(months - 1, -1, -1):
        month_index = now.month - 1 - offset
        year = now.year + month_index // 12
        month = month_index % 12 + 1
        start = timezone.make_aware(datetime.datetime(year, month, 1))
        if month == 12:
            end = timezone.make_aware(datetime.datetime(year + 1, 1, 1))
        else:
            end = timezone.make_aware(datetime.datetime(year, month + 1, 1))

        total = int(
            qs.filter(paid_at__gte=start, paid_at__lt=end).aggregate(
                total=Sum("annual_fee_inr"),
            )["total"]
            or 0
        )
        month_label = start.strftime("%b %Y")
        trend.append({"month": month_label, "collectedInr": total})
    return trend


def aggregate_platform_billing_stats() -> dict:
    """Platform-wide totals from materialized TenantLicenseSummary rows."""
    from apps.organizations.models import StudentPlatformSubscription

    agg = TenantLicenseSummary.objects.filter(tenant__is_active=True).aggregate(
        students=Sum("active_student_count"),
        annual=Sum("annual_subscription_inr"),
        collected=Sum("collected_subscription_inr"),
    )
    year = current_academic_year()
    sub_qs = StudentPlatformSubscription.objects.filter(academic_year=year, is_active=True)
    paid = sub_qs.filter(status=StudentPlatformSubscriptionStatus.PAID).count()
    unpaid = sub_qs.filter(status=StudentPlatformSubscriptionStatus.UNPAID).count()
    overdue = sub_qs.filter(status=StudentPlatformSubscriptionStatus.OVERDUE).count()

    return {
        "totalStudents": int(agg["students"] or 0),
        "annualSubscriptionInr": int(agg["annual"] or 0),
        "collectedSubscriptionInr": int(agg["collected"] or 0),
        "paid": paid,
        "unpaid": unpaid,
        "overdue": overdue,
    }


def billing_dict_for_tenant(tenant_id) -> dict:
    """Unified billing breakdown for APIs — reads materialized DB fields."""
    from apps.organizations.queries import branch as branch_q

    tenant = Tenant.objects.filter(pk=tenant_id, is_active=True).first()
    if tenant is None:
        raise ValueError("Tenant not found.")

    summary, _ = TenantLicenseSummary.objects.get_or_create(tenant=tenant)
    tenant_pricing = pricing.pricing_for_tenant(tenant_id)
    net_unit = tenant_pricing["unitPricePerStudentInr"]
    year = current_academic_year()

    branches = []
    for branch in branch_q.list_branches(tenant_id):
        subs = StudentPlatformSubscription.objects.filter(
            tenant_id=tenant_id,
            branch_id=branch.pk,
            academic_year=year,
            is_active=True,
        )
        count = subs.count()
        paid_count = subs.filter(status=StudentPlatformSubscriptionStatus.PAID).count()
        branches.append({
            "branchId": str(branch.pk),
            "branchName": branch.name,
            "studentCount": count,
            "unitPricePerStudentInr": net_unit,
            "annualSubscriptionInr": count * net_unit,
            "paidCount": paid_count,
            "unpaidCount": count - paid_count,
        })

    annual = summary.annual_subscription_inr
    collected = summary.collected_subscription_inr

    return {
        "plan": tenant_pricing["plan"],
        "listPricePerStudentInr": tenant_pricing["listPricePerStudentInr"],
        "discountPercent": tenant_pricing["discountPercent"],
        "unitPricePerStudentInr": net_unit,
        "studentCount": summary.active_student_count,
        "annualSubscriptionInr": annual,
        "collectedSubscriptionInr": collected,
        "outstandingInr": max(0, annual - collected),
        "branches": branches,
        "licensesPurchased": summary.licenses_purchased,
        "licensesConsumed": summary.licenses_consumed,
        "unlicensedStudents": summary.unlicensed_active_count,
    }
