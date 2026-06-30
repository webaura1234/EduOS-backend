"""Queries for platform-owner student subscription roster."""

from __future__ import annotations

import math

from django.db.models import Count, Q, Sum

from apps.organizations.billing.student_subscription import current_academic_year
from apps.organizations.enums import StudentPlatformSubscriptionStatus
from apps.organizations.models import Branch, StudentPlatformSubscription, Tenant


def _base_queryset(*, academic_year: str | None = None):
    year = academic_year or current_academic_year()
    return (
        StudentPlatformSubscription.objects.filter(academic_year=year, is_active=True)
        .select_related("tenant", "branch", "student_user")
        .order_by("tenant__name", "branch__name", "student_user__first_name", "student_user__last_name")
    )


def list_student_subscriptions(
    *,
    tenant_id=None,
    branch_id=None,
    plan="all",
    status="all",
    q=None,
    page=1,
    page_size=50,
    skip_meta=False,
):
    qs = _base_queryset()

    if tenant_id:
        qs = qs.filter(tenant_id=tenant_id)
    if branch_id:
        qs = qs.filter(branch_id=branch_id)
    if plan and plan != "all":
        qs = qs.filter(plan=plan)
    if status and status != "all":
        qs = qs.filter(status=status)
    if q:
        term = q.strip()
        if term:
            qs = qs.filter(
                Q(student_user__first_name__icontains=term)
                | Q(student_user__last_name__icontains=term)
                | Q(student_user__custom_login_id__icontains=term)
            )

    page = max(1, int(page))
    page_size = min(200, max(1, int(page_size)))
    offset = (page - 1) * page_size
    rows = list(qs[offset : offset + page_size])

    if skip_meta:
        # Page-only change — minimal count query for pagination, skip heavy stats.
        total = qs.count()
        stats = {
            "totalStudents": total,
            "paid": 0,
            "unpaid": 0,
            "overdue": 0,
            "annualSubscriptionInr": 0,
            "collectedSubscriptionInr": 0,
        }
    else:
        # Single aggregate replaces 4 separate queries (count + 3 filter counts + sum).
        agg = qs.aggregate(
            total=Count("id"),
            annual=Sum("annual_fee_inr"),
            collected=Sum("annual_fee_inr", filter=Q(status=StudentPlatformSubscriptionStatus.PAID)),
            paid_count=Count("id", filter=Q(status=StudentPlatformSubscriptionStatus.PAID)),
            unpaid_count=Count("id", filter=Q(status=StudentPlatformSubscriptionStatus.UNPAID)),
            overdue_count=Count("id", filter=Q(status=StudentPlatformSubscriptionStatus.OVERDUE)),
        )
        total = agg["total"] or 0
        stats = {
            "totalStudents": total,
            "paid": agg["paid_count"] or 0,
            "unpaid": agg["unpaid_count"] or 0,
            "overdue": agg["overdue_count"] or 0,
            "annualSubscriptionInr": int(agg["annual"] or 0),
            "collectedSubscriptionInr": int(agg["collected"] or 0),
        }

    return {
        "rows": rows,
        "pagination": {
            "page": page,
            "pageSize": page_size,
            "total": total,
            "totalPages": max(1, math.ceil(total / page_size)) if total else 1,
        },
        "stats": stats,
    }


def filter_options(*, tenant_id=None) -> dict:
    tenants = list(
        Tenant.objects.filter(is_active=True)
        .order_by("name")
        .values("id", "name", "subdomain")
    )
    branch_qs = Branch.objects.filter(is_active=True).order_by("name")
    if tenant_id:
        branch_qs = branch_qs.filter(tenant_id=tenant_id)
    branches = list(branch_qs.values("id", "name", "tenant_id"))
    return {
        "tenants": [
            {"id": str(t["id"]), "name": t["name"], "subdomain": t["subdomain"]}
            for t in tenants
        ],
        "branches": [
            {
                "id": str(b["id"]),
                "name": b["name"],
                "tenantId": str(b["tenant_id"]),
            }
            for b in branches
        ],
    }


def get_subscription_for_action(subscription_id):
    try:
        return _base_queryset().get(pk=subscription_id)
    except StudentPlatformSubscription.DoesNotExist:
        return None
