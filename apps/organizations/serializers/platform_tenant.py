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
from apps.organizations.billing import pricing
from apps.organizations.billing.platform_pricing import (
    amount_due_inr,
    annual_subscription_inr,
    collected_subscription_inr,
)
from apps.organizations.plan_catalog import normalize_plan
from apps.organizations.queries import platform_tenant as q


def tenant_summary(tenant) -> dict:
    """Present a Tenant as the camelCase `PlatformTenantSummary` the frontend expects."""
    from apps.organizations.models import TenantLicenseSummary

    subscription = getattr(tenant, "subscription", None)
    super_admin = get_first_user_by_role_in_tenant(tenant.id, Role.SUPER_ADMIN)
    plan = normalize_plan(subscription.plan if subscription else "standard")
    student_count = count_active_by_role_in_tenant(tenant.id, Role.STUDENT)
    billing_status = subscription.billing_status if subscription else "trial"
    tenant_pricing = pricing.pricing_for_tenant(tenant.id, plan)

    license_summary = TenantLicenseSummary.objects.filter(tenant_id=tenant.id).first()
    if license_summary and license_summary.active_student_count > 0:
        annual_inr = license_summary.annual_subscription_inr
        collected_inr = license_summary.collected_subscription_inr
        student_count = license_summary.active_student_count
    else:
        annual_inr = annual_subscription_inr(
            plan=plan, student_count=student_count, tenant_id=tenant.id
        )
        collected_inr = collected_subscription_inr(
            billing_status=billing_status, annual_inr=annual_inr
        )

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
        "listPricePerStudentInr": tenant_pricing["listPricePerStudentInr"],
        "discountPercent": tenant_pricing["discountPercent"],
        "unitPricePerStudentInr": tenant_pricing["unitPricePerStudentInr"],
    }


def platform_stats_from_summaries(summaries: list[dict]) -> dict:
    from apps.organizations.billing.billing_refresh import aggregate_platform_billing_stats

    billing_stats = aggregate_platform_billing_stats()
    if billing_stats["totalStudents"] > 0:
        return {
            "totalStudents": billing_stats["totalStudents"],
            "annualSubscriptionInr": billing_stats["annualSubscriptionInr"],
            "collectedSubscriptionInr": billing_stats["collectedSubscriptionInr"],
            "billingStats": {
                "paid": billing_stats["paid"],
                "overdue": billing_stats["overdue"],
                "trial": billing_stats["unpaid"],
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
    plan = serializers.ChoiceField(choices=["standard", "ai"])


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
