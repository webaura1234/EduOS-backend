"""
Platform-owner tenant serializers + presenter.

Output matches @eduos/types `PlatformTenantSummary`. Input matches
`CreatePlatformTenantInput` (the 6-step wizard) and `PlatformTenantStatusActionInput`.
"""

from rest_framework import serializers

from apps.accounts.models.user import Role
from apps.accounts.queries.session import count_active_sessions_for_tenant
from apps.accounts.queries.user import (
    count_active_by_role_in_tenant,
    get_first_user_by_role_in_tenant,
)
from apps.organizations.billing.platform_pricing import (
    amount_due_inr,
    annual_subscription_inr,
    collected_subscription_inr,
)
from apps.organizations.billing.student_subscription import current_academic_year
from apps.organizations.models import StudentPlatformSubscription
from apps.organizations.enums import StudentPlatformSubscriptionStatus
from apps.organizations.queries import platform_tenant as q


def tenant_summary(tenant) -> dict:
    """Present a Tenant as the camelCase `PlatformTenantSummary` the frontend expects."""
    subscription = getattr(tenant, "subscription", None)
    super_admin = get_first_user_by_role_in_tenant(tenant.id, Role.SUPER_ADMIN)
    plan = subscription.plan if subscription else "starter"
    student_count = count_active_by_role_in_tenant(tenant.id, Role.STUDENT)
    billing_status = subscription.billing_status if subscription else "trial"
    annual_inr = annual_subscription_inr(plan=plan, student_count=student_count)

    year = current_academic_year()
    student_sub_qs = StudentPlatformSubscription.objects.filter(
        tenant_id=tenant.id,
        academic_year=year,
        is_active=True,
    )
    if student_sub_qs.exists():
        from django.db.models import Sum, Q

        agg = student_sub_qs.aggregate(
            annual=Sum("annual_fee_inr"),
            collected=Sum(
                "annual_fee_inr",
                filter=Q(status=StudentPlatformSubscriptionStatus.PAID),
            ),
        )
        annual_inr = int(agg["annual"] or annual_inr)
        collected_inr = int(agg["collected"] or 0)
    else:
        collected_inr = collected_subscription_inr(billing_status=billing_status, annual_inr=annual_inr)
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "subdomain": tenant.subdomain,
        "plan": plan,
        "institutionType": tenant.institution_type,
        "city": tenant.city,
        "state": tenant.state,
        "status": q.to_ui_status(tenant.status),
        "superAdminName": super_admin.full_name if super_admin else "",
        "superAdminPhone": super_admin.phone if super_admin else "",
        "createdAt": tenant.created_at.isoformat() if tenant.created_at else None,
        "branchCount": q.branch_count(tenant.id),
        "studentCount": student_count,
        "activeSessions": count_active_sessions_for_tenant(tenant.id),
        "billingStatus": billing_status,
        "annualSubscriptionInr": annual_inr,
        "collectedSubscriptionInr": collected_inr,
        "amountDueInr": amount_due_inr(billing_status=billing_status, annual_inr=annual_inr),
    }


def platform_stats_from_summaries(summaries: list[dict]) -> dict:
    from apps.organizations.billing.student_subscription import aggregate_platform_subscription_stats

    sub_stats = aggregate_platform_subscription_stats()
    if sub_stats["totalStudents"] > 0:
        return {
            "totalStudents": sub_stats["totalStudents"],
            "annualSubscriptionInr": sub_stats["annualSubscriptionInr"],
            "collectedSubscriptionInr": sub_stats["collectedSubscriptionInr"],
            "billingStats": {
                "paid": sub_stats["paid"],
                "overdue": sub_stats["overdue"],
                "trial": sub_stats["unpaid"],
            },
        }

    total_students = sum(int(s.get("studentCount") or 0) for s in summaries)
    annual_total = sum(int(s.get("annualSubscriptionInr") or 0) for s in summaries)
    collected = sum(int(s.get("collectedSubscriptionInr") or 0) for s in summaries)
    billing = {"paid": 0, "overdue": 0, "trial": 0}
    for s in summaries:
        bs = s.get("billingStatus") or "trial"
        if bs in billing:
            billing[bs] += 1
    return {
        "totalStudents": total_students,
        "annualSubscriptionInr": annual_total,
        "collectedSubscriptionInr": collected,
        "billingStats": billing,
    }


# ── Input ─────────────────────────────────────────────────────────────────────
class _OverviewSerializer(serializers.Serializer):
    institutionName = serializers.CharField(max_length=255)
    subdomain = serializers.CharField(max_length=63)
    institutionType = serializers.ChoiceField(choices=["school", "college"])
    plan = serializers.ChoiceField(choices=["starter", "growth", "enterprise"])


class _InviteSerializer(serializers.Serializer):
    superAdminName = serializers.CharField(max_length=200)
    superAdminPhone = serializers.CharField(max_length=20)


class CreatePlatformTenantSerializer(serializers.Serializer):
    overview = _OverviewSerializer()
    invite = _InviteSerializer()
    address = serializers.DictField(required=False, default=dict)
    branches = serializers.DictField(required=False, default=dict)
    features = serializers.DictField(required=False, default=dict)
    integrations = serializers.DictField(required=False, default=dict)


class TenantStatusActionSerializer(serializers.Serializer):
    tenantId = serializers.UUIDField()
    action = serializers.ChoiceField(choices=["activate", "deactivate"])
