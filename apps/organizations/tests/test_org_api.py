"""API tests for the organizations super-admin endpoints."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.organizations.models import InstitutionType
from apps.organizations.tests.factories import (
    BranchFactory,
    PlanSubscriptionFactory,
    TenantFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def tenant():
    return TenantFactory(institution_type=InstitutionType.SCHOOL)


@pytest.fixture
def super_admin(tenant):
    return UserFactory(role=Role.SUPER_ADMIN, tenant=tenant, branch=None,
                       phone="+919900000001", custom_login_id=None, must_change_password=False)


@pytest.fixture
def client(super_admin):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(super_admin)}")
    return c


# ── Branches ──────────────────────────────────────────────────────────────────
def test_branches_list_and_create(client, tenant):
    BranchFactory(tenant=tenant, name="Main Campus", code="MC", is_primary=True)

    resp = client.get(reverse("organizations:branches"))
    assert resp.status_code == 200
    body = resp.json().get("data", resp.json())
    assert len(body["branches"]) == 1
    assert body["branches"][0]["isActive"] is True  # camelCase contract

    create = client.post(reverse("organizations:branches"),
                         {"name": "North Campus", "code": "NC", "city": "Pune"}, format="json")
    assert create.status_code == 201
    cbody = create.json().get("data", create.json())
    assert cbody["branch"]["name"] == "North Campus"


def test_branch_duplicate_name_rejected(client, tenant):
    BranchFactory(tenant=tenant, name="Main Campus", code="MC")
    resp = client.post(reverse("organizations:branches"),
                       {"name": "Main Campus", "code": "X1", "city": "X"}, format="json")
    assert resp.status_code == 400


def test_branch_set_active(client, tenant):
    branch = BranchFactory(tenant=tenant, name="North", code="NC")
    resp = client.patch(reverse("organizations:branch-actions"),
                        {"action": "set_active", "branchId": str(branch.id), "isActive": False},
                        format="json")
    assert resp.status_code == 200
    branch.refresh_from_db()
    assert branch.is_active is False


def test_branches_forbidden_for_non_super_admin(tenant):
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, phone="+919900000099",
                        custom_login_id=None, must_change_password=False)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(admin)}")
    assert c.get(reverse("organizations:branches")).status_code == 403


# ── Institution settings ──────────────────────────────────────────────────────
def test_institution_settings_get_and_patch(client):
    resp = client.get(reverse("organizations:institution-settings"))
    assert resp.status_code == 200

    patch = client.patch(reverse("organizations:institution-settings"),
                         {"institutionName": "Greenfield Academy",
                          "address": {"line1": "1 MG Rd", "city": "Pune", "state": "MH", "pincode": "411001"}},
                         format="json")
    assert patch.status_code == 200
    body = patch.json().get("data", patch.json())
    assert body["institutionName"] == "Greenfield Academy"
    assert body["address"]["city"] == "Pune"


def test_parent_portal_toggle_rejected_for_school(client):
    resp = client.patch(reverse("organizations:institution-settings"),
                       {"parentPortalEnabled": False}, format="json")
    assert resp.status_code == 400


def test_type_immutable_after_go_live(client):
    # Go live first
    live = client.post(reverse("organizations:institution-settings"), {"action": "go_live"}, format="json")
    assert live.status_code == 200
    assert live.json().get("data", live.json())["goLiveAt"] is not None

    # Then try to change type → blocked
    resp = client.patch(reverse("organizations:institution-settings"),
                       {"institutionType": "college"}, format="json")
    assert resp.status_code == 400


# ── Plan ──────────────────────────────────────────────────────────────────────
def test_plan_get(client, tenant):
    PlanSubscriptionFactory(tenant=tenant, plan="growth", student_limit=1500)
    resp = client.get(reverse("organizations:plan"))
    assert resp.status_code == 200
    body = resp.json().get("data", resp.json())
    assert body["current"]["tier"] == "growth"
    assert body["current"]["limits"]["students"] == 1500


# ── Subdomain check ───────────────────────────────────────────────────────────
def test_subdomain_check(client):
    taken = TenantFactory(subdomain="greenfield").subdomain
    url = reverse("organizations:subdomain-check")

    r_taken = client.get(url, {"q": taken})
    assert r_taken.json().get("data", r_taken.json())["available"] is False

    r_free = client.get(url, {"q": "brand-new-school"})
    assert r_free.json().get("data", r_free.json())["available"] is True

    r_bad = client.get(url, {"q": "Bad_Subdomain!"})
    assert r_bad.json().get("data", r_bad.json())["valid"] is False
