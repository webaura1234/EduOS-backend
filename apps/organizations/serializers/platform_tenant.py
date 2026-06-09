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
from apps.organizations.queries import platform_tenant as q


def tenant_summary(tenant) -> dict:
    """Present a Tenant as the camelCase `PlatformTenantSummary` the frontend expects."""
    subscription = getattr(tenant, "subscription", None)
    super_admin = get_first_user_by_role_in_tenant(tenant.id, Role.SUPER_ADMIN)
    return {
        "id": str(tenant.id),
        "name": tenant.name,
        "subdomain": tenant.subdomain,
        "plan": subscription.plan if subscription else "starter",
        "institutionType": tenant.institution_type,
        "city": tenant.city,
        "state": tenant.state,
        "status": q.to_ui_status(tenant.status),
        "superAdminName": super_admin.full_name if super_admin else "",
        "superAdminPhone": super_admin.phone if super_admin else "",
        "createdAt": tenant.created_at.isoformat() if tenant.created_at else None,
        "branchCount": q.branch_count(tenant.id),
        "studentCount": count_active_by_role_in_tenant(tenant.id, Role.STUDENT),
        "activeSessions": count_active_sessions_for_tenant(tenant.id),
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
