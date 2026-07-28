"""Materialize tenant billing from Licensing + PlanSubscription pricing.

Collected = sum(LicensePayment.amount_inr)
Annual = licenses_consumed × net_unit_price
Pending = unlicensed_active_count × net_unit_price
"""

from __future__ import annotations

import datetime

from django.db.models import Sum
from django.utils import timezone

from apps.organizations.billing import pricing
from apps.organizations.billing import seat_billing
from apps.organizations.models import (
    LicensePayment,
    Tenant,
    TenantLicensePricing,
    TenantLicenseSummary,
)


def refresh_tenant_billing(tenant_id, *, user=None) -> TenantLicenseSummary:
    """Recompute net unit price and summary subscription totals from licenses/payments."""
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

    summary = alloc.refresh_summary(tenant)
    summary.active_student_count = summary.licenses_consumed
    summary.annual_subscription_inr = seat_billing.annual_for_consumed(
        licenses_consumed=summary.licenses_consumed,
        net_unit=net_unit,
    )
    summary.collected_subscription_inr = seat_billing.collected_from_payments(tenant_id=tenant_id)
    summary.pending_amount_inr = seat_billing.pending_for_unlicensed(
        unlicensed_count=summary.unlicensed_active_count,
        net_unit=net_unit,
    )
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
    """Sum of LicensePayment amounts grouped by calendar month."""
    qs = LicensePayment.objects.filter(is_active=True)
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
            qs.filter(paid_at__gte=start.date(), paid_at__lt=end.date()).aggregate(
                total=Sum("amount_inr"),
            )["total"]
            or 0
        )
        month_label = start.strftime("%b %Y")
        trend.append({"month": month_label, "collectedInr": total})
    return trend


def aggregate_platform_billing_stats() -> dict:
    """Platform-wide totals from TenantLicenseSummary + license seat counts."""
    agg = TenantLicenseSummary.objects.filter(tenant__is_active=True).aggregate(
        students=Sum("active_student_count"),
        annual=Sum("annual_subscription_inr"),
        collected=Sum("collected_subscription_inr"),
        purchased=Sum("licenses_purchased"),
        consumed=Sum("licenses_consumed"),
        unlicensed=Sum("unlicensed_active_count"),
    )
    licensed = int(agg["consumed"] or 0)
    unlicensed = int(agg["unlicensed"] or 0)

    return {
        "totalStudents": int(agg["students"] or 0),
        "annualSubscriptionInr": int(agg["annual"] or 0),
        "collectedSubscriptionInr": int(agg["collected"] or 0),
        # License-shaped stats (aliases keep older FE keys working).
        "licensed": licensed,
        "unlicensed": unlicensed,
        "licensesPurchased": int(agg["purchased"] or 0),
        "licensesConsumed": licensed,
        "paid": licensed,
        "unpaid": unlicensed,
        "overdue": 0,
    }


def billing_dict_for_tenant(tenant_id) -> dict:
    """Unified billing breakdown for APIs — licenses + payments."""
    tenant = Tenant.objects.filter(pk=tenant_id, is_active=True).first()
    if tenant is None:
        raise ValueError("Tenant not found.")

    summary, _ = TenantLicenseSummary.objects.get_or_create(tenant=tenant)
    tenant_pricing = pricing.pricing_for_tenant(tenant_id)
    net_unit = tenant_pricing["unitPricePerStudentInr"]
    branches = seat_billing.branch_license_counts(tenant_id)

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
        "remainingSeats": max(0, summary.licenses_purchased - summary.licenses_consumed),
    }
