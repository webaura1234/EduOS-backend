"""API tests for platform-owner tenant management."""

import pytest
from django.urls import reverse
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from apps.accounts.models.token import RefreshToken
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.organizations.models import Tenant
from apps.organizations.tests.factories import TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def platform_owner():
    return UserFactory(role=Role.PLATFORM_OWNER, tenant=None, branch=None,
                       phone="+919700000000", custom_login_id=None, must_change_password=False)


@pytest.fixture
def client(platform_owner):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(platform_owner)}")
    return c


CREATE_PAYLOAD = {
    "overview": {"institutionName": "New School", "subdomain": "newschool",
                 "institutionType": "school", "plan": "growth"},
    "invite": {"superAdminName": "Asha Rao", "superAdminPhone": "+919812345678"},
    "address": {"city": "Pune", "state": "MH", "addressLine1": "1 MG Rd", "pincode": "411001"},
    "branches": {"hqCity": "Pune", "hqState": "MH", "entries": [{"name": "Main Campus", "assignees": []}]},
    "features": {"parentPortal": True, "onlineFees": True},
    "integrations": {"razorpay": True},
}


def _data(resp):
    return resp.json().get("data", resp.json())


def test_create_tenant_provisions_everything(client):
    resp = client.post(reverse("organizations:platform-tenants"), CREATE_PAYLOAD, format="json")
    assert resp.status_code == 201
    summary = _data(resp)["tenant"]
    assert summary["subdomain"] == "newschool"
    assert summary["status"] == "pending"          # trial → pending
    assert summary["plan"] == "growth"
    assert summary["superAdminName"] == "Asha Rao"
    assert summary["branchCount"] == 1

    tenant = Tenant.objects.get(subdomain="newschool")
    assert hasattr(tenant, "subscription") and tenant.subscription.plan == "growth"
    assert tenant.tenant_settings is not None
    assert tenant.branches.count() == 1
    # Super-admin invite user created
    assert tenant.users.filter(role=Role.SUPER_ADMIN).count() == 1


def test_create_tenant_duplicate_subdomain_rejected(client):
    TenantFactory(subdomain="newschool")
    resp = client.post(reverse("organizations:platform-tenants"), CREATE_PAYLOAD, format="json")
    assert resp.status_code == 400


def test_list_tenants_with_stats_and_filter(client):
    TenantFactory(name="Alpha", subdomain="alpha", status="active", city="Pune")
    TenantFactory(name="Beta", subdomain="beta", status="trial", city="Delhi")

    resp = client.get(reverse("organizations:platform-tenants"))
    assert resp.status_code == 200
    body = _data(resp)
    assert body["stats"]["total"] == 2
    assert body["stats"]["active"] == 1
    assert body["stats"]["pending"] == 1
    assert "Pune" in body["filterOptions"]["cities"]

    # Filter by UI status → model status mapping
    only_active = _data(client.get(reverse("organizations:platform-tenants"), {"status": "active"}))
    assert len(only_active["tenants"]) == 1
    assert only_active["tenants"][0]["name"] == "Alpha"


def test_tenant_detail(client):
    t = TenantFactory(subdomain="detail-co")
    resp = client.get(reverse("organizations:platform-tenant-detail", kwargs={"tenant_id": t.id}))
    assert resp.status_code == 200
    assert _data(resp)["tenant"]["subdomain"] == "detail-co"


def test_deactivate_kills_sessions(client):
    tenant = TenantFactory(subdomain="killme", status="active")
    member = UserFactory(role=Role.ADMIN, tenant=tenant, phone="+919811111222",
                         custom_login_id=None, must_change_password=False)
    # Two active sessions for the tenant.
    RefreshToken.objects.create(user=member, token="tok-1",
                                expires_at=timezone.now() + timedelta(days=1))
    RefreshToken.objects.create(user=member, token="tok-2",
                                expires_at=timezone.now() + timedelta(days=1))

    resp = client.patch(reverse("organizations:platform-tenant-actions"),
                        {"tenantId": str(tenant.id), "action": "deactivate"}, format="json")
    assert resp.status_code == 200
    body = _data(resp)
    assert body["sessionsTerminated"] == 2
    assert body["tenant"]["status"] == "inactive"
    assert RefreshToken.objects.filter(user=member, is_revoked=False).count() == 0

    tenant.refresh_from_db()
    assert tenant.status == "deactivated" and tenant.deactivated_at is not None


def test_activate_tenant(client):
    tenant = TenantFactory(subdomain="wakeup", status="suspended")
    resp = client.patch(reverse("organizations:platform-tenant-actions"),
                        {"tenantId": str(tenant.id), "action": "activate"}, format="json")
    assert resp.status_code == 200
    assert _data(resp)["tenant"]["status"] == "active"


def test_forbidden_for_non_platform_owner():
    tenant = TenantFactory()
    super_admin = UserFactory(role=Role.SUPER_ADMIN, tenant=tenant, phone="+919733333333",
                              custom_login_id=None, must_change_password=False)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(super_admin)}")
    assert c.get(reverse("organizations:platform-tenants")).status_code == 403
