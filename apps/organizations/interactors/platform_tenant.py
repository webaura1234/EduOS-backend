"""
Platform-owner tenant interactors.

Business logic for onboarding a tenant and changing its lifecycle status.
Views call these; all DB access is delegated to the queries layer. Writes are
wrapped in a transaction so a partially-provisioned tenant is never persisted.
"""

import logging

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.accounts.models.user import Role
from apps.accounts.queries.session import (
    count_active_sessions_for_tenant,
    revoke_tokens_for_tenant,
)
from apps.accounts.queries.user import create_invited_user
from apps.organizations.queries import institution as inst_q
from apps.organizations.queries import platform_tenant as q

logger = logging.getLogger("apps.organizations.interactors.platform_tenant")

# Per-tier subscription limits applied at onboarding.
_PLAN_LIMITS = {
    "starter": {"student_limit": 500, "storage_limit_gb": 10, "sms_quota_per_month": 1000},
    "growth": {"student_limit": 1500, "storage_limit_gb": 50, "sms_quota_per_month": 5000},
    "enterprise": {"student_limit": 100000, "storage_limit_gb": 500, "sms_quota_per_month": 100000},
}


@transaction.atomic
def create_tenant(payload: dict, user=None):
    """
    Provision a new tenant from the onboarding wizard payload:
    Tenant + TenantSettings + PlanSubscription + primary Branch + super-admin invite.

    Raises ValidationError on a duplicate subdomain or bad input.
    Returns the created Tenant.
    """
    overview = payload["overview"]
    address = payload.get("address", {})
    invite = payload["invite"]
    branches = payload.get("branches", {})
    features = payload.get("features", {})

    subdomain = overview["subdomain"].strip().lower()
    if inst_q.subdomain_taken(subdomain):
        raise ValidationError("Subdomain is already taken.")

    plan = overview["plan"]
    institution_type = overview["institutionType"]
    city = address.get("city") or branches.get("hqCity", "")
    state = address.get("state") or branches.get("hqState", "")

    try:
        tenant = q.create_tenant(
            name=overview["institutionName"],
            subdomain=subdomain,
            institution_type=institution_type,
            city=city,
            state=state,
            address_line1=address.get("addressLine1", ""),
            address_line2=address.get("addressLine2", ""),
            postal_code=address.get("pincode", ""),
            # Parent portal is always on for schools; wizard-driven for colleges.
            parent_access_enabled=(institution_type == "school") or bool(features.get("parentPortal")),
            settings_json={"features": features, "integrations": payload.get("integrations", {})},
            user=user,
        )
    except IntegrityError as exc:  # subdomain race
        raise ValidationError("Subdomain is already taken.") from exc

    q.create_settings(tenant, user=user)
    q.create_subscription(
        tenant, plan=plan, limits=_PLAN_LIMITS.get(plan, _PLAN_LIMITS["starter"]), user=user
    )

    # Primary branch (use first wizard entry name if provided, else "Main Campus").
    entries = branches.get("entries") or []
    primary_name = entries[0]["name"] if entries else "Main Campus"
    q.create_primary_branch(tenant, name=primary_name, city=city, state=state, user=user)

    # Super-admin invite (unusable password until they accept the invite).
    create_invited_user(
        first_name=invite["superAdminName"],
        last_name="",
        role=Role.SUPER_ADMIN,
        tenant_id=tenant.id,
        branch_id=None,
        phone=invite["superAdminPhone"],
        custom_login_id=None,
        email=None,
        created_by=user,
    )

    logger.info("Tenant provisioned: %s (%s) plan=%s", tenant.name, subdomain, plan)
    return tenant


@transaction.atomic
def change_status(tenant_id, action: str, user=None):
    """
    Activate or deactivate a tenant. Deactivation kills all active sessions for the
    tenant's users (EC-TEN-04). Returns (tenant, sessions_terminated, message).
    """
    tenant = q.get_tenant(tenant_id)
    if tenant is None:
        raise ValidationError("Tenant not found.")

    if action == "activate":
        tenant = q.set_status(tenant, model_status="active", user=user)
        return tenant, 0, f"{tenant.name} activated."

    if action == "deactivate":
        terminated = revoke_tokens_for_tenant(tenant.id)
        tenant = q.set_status(tenant, model_status="deactivated", user=user)
        return tenant, terminated, f"{tenant.name} deactivated. {terminated} session(s) terminated."

    raise ValidationError(f"Unsupported action '{action}'.")


def active_session_count(tenant_id) -> int:
    return count_active_sessions_for_tenant(tenant_id)
