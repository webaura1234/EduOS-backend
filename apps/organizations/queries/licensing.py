"""Read queries for the licensing module — platform overview + tenant detail."""

from __future__ import annotations

import datetime

from django.db.models import Sum
from django.utils import timezone

from apps.organizations.billing import license_allocator as alloc
from apps.organizations.billing import pricing
from apps.organizations.billing.billing_refresh import billing_dict_for_tenant
from apps.organizations.billing.platform_pricing import unit_price_for_tenant
from apps.organizations.enums import StudentLicenseStatus, SubscriptionPeriodStatus
from apps.organizations.models import (
    LicenseInvoice,
    LicensePayment,
    StudentLicense,
    Tenant,
    TenantLicenseSummary,
)
from apps.organizations.plan_catalog import normalize_plan
from apps.organizations.queries import branch as branch_q
from apps.organizations.serializers.licensing import (
    invoice_dict,
    payment_dict,
    period_dict,
    student_license_dict,
    summary_dict,
)

RENEWAL_WINDOW_DAYS = 60


def _tenant_summary(tenant: Tenant) -> TenantLicenseSummary:
    summary, _ = TenantLicenseSummary.objects.select_related(
        "current_period",
    ).get_or_create(tenant=tenant)
    if summary.current_period is None:
        period = alloc.get_current_period(tenant.pk)
        if period:
            summary.current_period = period
            summary.save(update_fields=["current_period", "updated_at"])
    return summary


def _school_billing_row(tenant: Tenant, summary: TenantLicenseSummary) -> dict:
    """Per-school row for platform billing overview — materialized totals + pricing."""
    subscription = getattr(tenant, "subscription", None)
    plan = normalize_plan(subscription.plan if subscription else "standard")
    tenant_pricing = pricing.pricing_for_tenant(tenant.pk, plan)
    price = unit_price_for_tenant(tenant.pk)
    period = summary.current_period

    return {
        "tenantId": str(tenant.pk),
        "tenantName": tenant.name,
        "subdomain": tenant.subdomain,
        "plan": tenant_pricing["plan"],
        "listPricePerStudentInr": tenant_pricing["listPricePerStudentInr"],
        "discountPercent": tenant_pricing["discountPercent"],
        "unitPricePerStudentInr": tenant_pricing["unitPricePerStudentInr"],
        **summary_dict(summary, unit_price=price),
        "periodEndDate": period.end_date.isoformat() if period else None,
    }


def platform_overview() -> dict:
    """Global KPIs + per-school billing rows for the Platform Owner."""
    tenants = list(
        Tenant.objects.filter(is_active=True)
        .select_related("subscription")
        .order_by("name"),
    )
    summaries = {
        s.tenant_id: s
        for s in TenantLicenseSummary.objects.select_related("current_period").filter(
            tenant__in=tenants,
        )
    }

    license_revenue = (
        LicensePayment.objects.filter(is_active=True)
        .aggregate(total=Sum("amount_inr"))["total"] or 0
    )

    today = timezone.localdate()
    renewal_cutoff = today + datetime.timedelta(days=RENEWAL_WINDOW_DAYS)

    rows = []
    total_licensed = 0
    total_unlicensed = 0
    total_students = 0
    total_annual = 0
    total_collected = 0
    total_outstanding = 0
    upcoming_renewals = []

    for tenant in tenants:
        summary = summaries.get(tenant.pk)
        if summary is None:
            summary = _tenant_summary(tenant)
        price = unit_price_for_tenant(tenant.pk)
        period = summary.current_period

        total_licensed += summary.licenses_consumed
        total_unlicensed += summary.unlicensed_active_count
        total_students += summary.active_student_count
        total_annual += summary.annual_subscription_inr
        total_collected += summary.collected_subscription_inr
        total_outstanding += max(0, summary.annual_subscription_inr - summary.collected_subscription_inr)

        rows.append(_school_billing_row(tenant, summary))

        if period and today <= period.end_date <= renewal_cutoff:
            upcoming_renewals.append({
                "tenantId": str(tenant.pk),
                "tenantName": tenant.name,
                "endDate": period.end_date.isoformat(),
                "licensesConsumed": summary.licenses_consumed,
                "renewalAmountInr": summary.licenses_consumed * price,
            })

    return {
        "kpis": {
            "totalSchools": len(tenants),
            "totalStudents": total_students,
            "annualSubscriptionInr": total_annual,
            "collectedSubscriptionInr": total_collected,
            "outstandingInr": total_outstanding,
            "totalLicensedStudents": total_licensed,
            "totalUnlicensedStudents": total_unlicensed,
            "pendingCollectionsInr": sum(r["pendingAmountInr"] for r in rows),
            "revenueCollectedInr": int(license_revenue),
            "schoolsRequiringBilling": sum(1 for r in rows if r["unlicensedStudents"] > 0),
        },
        "schools": rows,
        "upcomingRenewals": sorted(upcoming_renewals, key=lambda r: r["endDate"]),
    }


def branch_billing_rows(tenant: Tenant) -> list[dict]:
    """Per-branch counts for licensing operations (unlicensed queue amounts)."""
    price = unit_price_for_tenant(tenant.pk)
    rows = []
    for branch in branch_q.list_branches(tenant.pk):
        unlicensed = StudentLicense.objects.filter(
            tenant=tenant,
            branch_id=branch.pk,
            license_status=StudentLicenseStatus.UNLICENSED,
            student_user__is_active=True,
        ).count()
        rows.append({
            "id": str(branch.pk),
            "name": branch.name,
            "unlicensedCount": unlicensed,
            "pendingAmountInr": unlicensed * price,
        })
    return rows


def tenant_detail(tenant: Tenant, *, branch_id=None) -> dict:
    """One school: unified billing, unlicensed FIFO queue, payments, invoices."""
    summary = _tenant_summary(tenant)
    price = unit_price_for_tenant(tenant.pk)
    billing = billing_dict_for_tenant(tenant.pk)

    unlicensed_qs = (
        StudentLicense.objects.select_related("student_user", "branch")
        .filter(
            tenant=tenant,
            license_status=StudentLicenseStatus.UNLICENSED,
            student_user__is_active=True,
        )
    )
    if branch_id:
        unlicensed_qs = unlicensed_qs.filter(branch_id=branch_id)
    unlicensed = unlicensed_qs.order_by("enrolled_at")[:500]
    payments = (
        LicensePayment.objects.select_related("recorded_by", "branch")
        .filter(tenant=tenant, is_active=True)
        .order_by("-paid_at", "-created_at")[:100]
    )
    invoices = (
        LicenseInvoice.objects.filter(tenant=tenant, is_active=True)
        .order_by("-created_at")[:100]
    )

    return {
        "tenant": {
            "id": str(tenant.pk),
            "name": tenant.name,
            "subdomain": tenant.subdomain,
            "status": tenant.status,
        },
        "billing": billing,
        "summary": summary_dict(summary, unit_price=price),
        "branches": branch_billing_rows(tenant),
        "unlicensedQueue": [student_license_dict(r) for r in unlicensed],
        "payments": [payment_dict(p) for p in payments],
        "invoices": [invoice_dict(i) for i in invoices],
    }


def payment_history(tenant_id=None) -> list[dict]:
    qs = LicensePayment.objects.select_related("recorded_by", "branch").filter(is_active=True)
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    return [payment_dict(p) for p in qs.order_by("-paid_at", "-created_at")[:200]]


def tenant_scoped_summary(tenant: Tenant, *, branch_id=None) -> dict:
    """Summary for school dashboards. Branch admins get branch-filtered student
    counts on top of the tenant-level purchase/consumption totals."""
    summary = _tenant_summary(tenant)
    price = unit_price_for_tenant(tenant.pk)
    data = summary_dict(summary, unit_price=price)

    if branch_id:
        branch_unlicensed = StudentLicense.objects.filter(
            tenant=tenant,
            branch_id=branch_id,
            license_status=StudentLicenseStatus.UNLICENSED,
            student_user__is_active=True,
        ).count()
        data["branchUnlicensedStudents"] = branch_unlicensed
        data["branchPendingAmountInr"] = branch_unlicensed * price
    return data


def tenant_students(tenant: Tenant, *, status=None, branch_id=None, limit=500) -> list[dict]:
    qs = StudentLicense.objects.select_related("student_user", "branch").filter(tenant=tenant)
    if status in (StudentLicenseStatus.LICENSED, StudentLicenseStatus.UNLICENSED):
        qs = qs.filter(license_status=status)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    return [student_license_dict(r) for r in qs.order_by("enrolled_at")[:limit]]


def periods_for_tenant(tenant: Tenant) -> list[dict]:
    return [
        period_dict(p)
        for p in tenant.subscription_periods.filter(is_active=True).order_by("-start_date")
    ]


def active_period_status(tenant_id) -> str | None:
    period = alloc.get_current_period(tenant_id)
    if period:
        return period.status
    from apps.organizations.models import TenantSubscriptionPeriod

    if TenantSubscriptionPeriod.objects.filter(tenant_id=tenant_id, is_active=True).exists():
        return SubscriptionPeriodStatus.EXPIRED
    return None
