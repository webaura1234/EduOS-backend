"""Seat billing KPIs derived from Licensing + PlanSubscription pricing.

Not a third billing system — pure helpers for TenantLicenseSummary materialization.
"""

from __future__ import annotations

from django.db.models import Sum

from apps.organizations.billing import pricing
from apps.organizations.enums import StudentLicenseStatus
from apps.organizations.models import LicensePayment, StudentLicense


def collected_from_payments(*, tenant_id=None) -> int:
    """Sum of recorded LicensePayment.amount_inr (platform Collected KPI)."""
    qs = LicensePayment.objects.filter(is_active=True)
    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    return int(qs.aggregate(total=Sum("amount_inr"))["total"] or 0)


def annual_for_consumed(*, licenses_consumed: int, net_unit: int) -> int:
    """Billable annual = consumed seats × net plan unit price."""
    return max(0, int(licenses_consumed or 0)) * max(0, int(net_unit or 0))


def pending_for_unlicensed(*, unlicensed_count: int, net_unit: int) -> int:
    return max(0, int(unlicensed_count or 0)) * max(0, int(net_unit or 0))


def branch_license_counts(tenant_id) -> list[dict]:
    """Per-branch licensed vs unlicensed student counts from StudentLicense."""
    from apps.organizations.queries import branch as branch_q

    net_unit = pricing.net_unit_price_inr(tenant_id)
    rows = []
    for branch in branch_q.list_branches(tenant_id):
        qs = StudentLicense.objects.filter(
            tenant_id=tenant_id,
            branch_id=branch.pk,
            is_active=True,
        )
        licensed = qs.filter(license_status=StudentLicenseStatus.LICENSED).count()
        unlicensed = qs.filter(license_status=StudentLicenseStatus.UNLICENSED).count()
        total = licensed + unlicensed
        rows.append({
            "branchId": str(branch.pk),
            "branchName": branch.name,
            "studentCount": total,
            "licensedCount": licensed,
            "unlicensedCount": unlicensed,
            # Backward-compatible aliases used by older FE columns.
            "paidCount": licensed,
            "unpaidCount": unlicensed,
            "unitPricePerStudentInr": net_unit,
            "annualSubscriptionInr": licensed * net_unit,
        })
    return rows
