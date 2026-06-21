"""
Seed the database with the two reference institutions the frontend mock-data
assumes: Greenfield Academy (school) and Horizon Engineering College (college).

Each tenant is provisioned end-to-end: primary branch, TenantSettings,
PlanSubscription, TenantQuota counters, a super-admin, an admin, a faculty and a
student. A single platform_owner (no tenant) is also created.

Idempotent — safe to run repeatedly. Run with:  python seed_db.py
"""

import datetime
import os

import django
from django.conf import settings as dj_settings

# Bootstrap Django only when run as a standalone script (not under pytest, where
# Django is already configured).
if not dj_settings.configured:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    django.setup()

from apps.accounts.models.user import Role, User  # noqa: E402
from apps.organizations.models import (  # noqa: E402
    Branch,
    PlanSubscription,
    Tenant,
    TenantQuota,
    TenantSettings,
)

DEFAULT_PASSWORD = "Password123!"
PLATFORM_OWNER_PHONE = "+919000000001"
PLATFORM_OWNER_PASSWORD = "Platform@123"

# Per-plan subscription limits.
_PLAN_LIMITS = {
    "starter": dict(student_limit=500, storage_limit_gb=10, sms_quota_per_month=1000,
                    ai_token_quota_per_month=10000, api_rpm_limit=100),
    "growth": dict(student_limit=1500, storage_limit_gb=50, sms_quota_per_month=5000,
                   ai_token_quota_per_month=50000, api_rpm_limit=300),
}


def _ensure_password(user: User) -> None:
    if not user.has_usable_password() or not user.check_password(DEFAULT_PASSWORD):
        user.set_password(DEFAULT_PASSWORD)
        user.save(update_fields=["password"])


def _seed_user(*, role, tenant, branch, first_name, last_name,
               phone=None, custom_login_id=None) -> User:
    lookup = {"role": role, "tenant": tenant}
    if custom_login_id:
        lookup["custom_login_id"] = custom_login_id
    else:
        lookup["phone"] = phone
    user, created = User.objects.get_or_create(
        **lookup,
        defaults=dict(
            first_name=first_name, last_name=last_name, branch=branch,
            phone=phone, custom_login_id=custom_login_id,
            must_change_password=False, is_active=True,
        ),
    )
    _ensure_password(user)
    tag = "created" if created else "exists"
    ident = custom_login_id or phone
    print(f"  - {role:<13} {ident:<16} [{tag}]  (pass: {DEFAULT_PASSWORD})")
    return user


def _seed_quota(tenant, resource, soft_cap, hard_cap) -> None:
    TenantQuota.objects.get_or_create(
        tenant=tenant, resource=resource,
        period_start=datetime.date.today().replace(day=1),
        defaults=dict(period="month", usage=0, soft_cap=soft_cap, hard_cap=hard_cap),
    )


def seed_tenant(*, subdomain, name, institution_type, plan, city, state,
                student_id_label, faculty_id_label, parent_access_enabled,
                phone_prefix) -> Tenant:
    print(f"\n{name} ({institution_type}) — {subdomain}.eduos.app")

    tenant, _ = Tenant.objects.get_or_create(
        subdomain=subdomain,
        defaults=dict(name=name, institution_type=institution_type, status="active",
                      city=city, state=state, parent_access_enabled=parent_access_enabled),
    )
    branch, _ = Branch.objects.get_or_create(
        tenant=tenant, name="Main Campus",
        defaults=dict(code="MC", is_primary=True, city=city, state=state),
    )
    TenantSettings.objects.get_or_create(
        tenant=tenant,
        defaults=dict(student_id_label=student_id_label, faculty_id_label=faculty_id_label),
    )
    limits = _PLAN_LIMITS[plan]
    PlanSubscription.objects.get_or_create(
        tenant=tenant,
        defaults=dict(plan=plan, billing_status="trial", **limits),
    )
    _seed_quota(tenant, "students", soft_cap=int(limits["student_limit"] * 0.9),
                hard_cap=limits["student_limit"])
    _seed_quota(tenant, "sms_count", soft_cap=int(limits["sms_quota_per_month"] * 0.9),
                hard_cap=limits["sms_quota_per_month"])
    _seed_quota(tenant, "ai_tokens", soft_cap=int(limits["ai_token_quota_per_month"] * 0.9),
                hard_cap=limits["ai_token_quota_per_month"])

    _seed_user(role=Role.SUPER_ADMIN, tenant=tenant, branch=None,
               first_name=name.split()[0], last_name="SuperAdmin", phone=f"{phone_prefix}00")
    _seed_user(role=Role.ADMIN, tenant=tenant, branch=branch,
               first_name=name.split()[0], last_name="Admin", phone=f"{phone_prefix}10")
    _seed_user(role=Role.FACULTY, tenant=tenant, branch=branch,
               first_name="Priya", last_name="Patel", custom_login_id="FAC-001")
    _seed_user(role=Role.STUDENT, tenant=tenant, branch=branch,
               first_name="Rahul", last_name="Sharma", custom_login_id="STU-001")
    return tenant


def seed():
    print("Seeding database...")

    seed_tenant(
        subdomain="greenfield", name="Greenfield Academy", institution_type="school",
        plan="starter", city="Pune", state="Maharashtra",
        student_id_label="Roll Number", faculty_id_label="Employee ID",
        parent_access_enabled=True, phone_prefix="+9198765432",
    )
    seed_tenant(
        subdomain="horizon", name="Horizon Engineering College", institution_type="college",
        plan="growth", city="Bengaluru", state="Karnataka",
        student_id_label="Admission Number", faculty_id_label="Staff Code",
        parent_access_enabled=False, phone_prefix="+9197654321",
    )

    # Platform owner (SaaS operator) — no tenant. Matches frontend mock login hint.
    po, created = User.objects.get_or_create(
        role=Role.PLATFORM_OWNER, phone=PLATFORM_OWNER_PHONE,
        defaults=dict(first_name="Gopal", last_name="Platform Owner",
                      tenant=None, branch=None, must_change_password=False, is_active=True),
    )
    if not po.has_usable_password() or not po.check_password(PLATFORM_OWNER_PASSWORD):
        po.set_password(PLATFORM_OWNER_PASSWORD)
        po.save(update_fields=["password"])
    print(
        f"\nPlatform Owner {PLATFORM_OWNER_PHONE} "
        f"[{'created' if created else 'exists'}]  (pass: {PLATFORM_OWNER_PASSWORD})"
    )

    print("\nSeeding completed successfully!")


if __name__ == "__main__":
    seed()
