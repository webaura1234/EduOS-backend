"""Verifies seed_db.seed() provisions both reference institutions end-to-end."""

import pytest

from apps.accounts.models.user import Role, User
from apps.organizations.models import Tenant, TenantQuota

pytestmark = pytest.mark.django_db


def test_seed_provisions_both_institutions():
    import seed_db

    seed_db.seed()

    # School + college both exist with the right type/flags.
    school = Tenant.objects.get(subdomain="greenfield")
    college = Tenant.objects.get(subdomain="horizon")
    assert school.institution_type == "school"
    assert college.institution_type == "college"
    assert college.parent_access_enabled is False

    # Each tenant is fully provisioned.
    for tenant in (school, college):
        assert tenant.branches.filter(is_primary=True).exists()
        assert hasattr(tenant, "tenant_settings")
        assert hasattr(tenant, "subscription")
        assert TenantQuota.objects.filter(tenant=tenant).count() == 3  # students/sms/ai
        assert tenant.users.filter(role=Role.SUPER_ADMIN).exists()
        assert tenant.users.filter(role=Role.ADMIN).exists()
        assert tenant.users.filter(role=Role.FACULTY, custom_login_id="FAC-001").exists()
        assert tenant.users.filter(role=Role.STUDENT, custom_login_id="STU-001").exists()

    # Platform owner exists, tenant-less.
    assert User.objects.filter(role=Role.PLATFORM_OWNER, tenant__isnull=True).count() == 1

    # Idempotent — running again creates no duplicates.
    seed_db.seed()
    assert Tenant.objects.filter(subdomain="greenfield").count() == 1
    assert TenantQuota.objects.filter(tenant=school).count() == 3
