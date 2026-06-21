"""Super-admin branch-admin management — list / invite / activate / reassign."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role, User
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="college")
    branch = BranchFactory(tenant=tenant)
    branch2 = BranchFactory(tenant=tenant)
    super_admin = UserFactory(role=Role.SUPER_ADMIN, tenant=tenant, branch=None,
                              phone="+919765432100", custom_login_id=None,
                              must_change_password=False)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch,
                        first_name="Existing", last_name="Admin", phone="+919765432110",
                        custom_login_id=None, must_change_password=False)
    return dict(tenant=tenant, branch=branch, branch2=branch2,
                super_admin=super_admin, admin=admin)


def test_list_admins_and_branches(env):
    resp = _client(env["super_admin"]).get(reverse("accounts:admins"))
    assert resp.status_code == 200, resp.content
    data = resp.json()["data"]
    assert len(data["admins"]) == 1
    assert data["admins"][0]["name"] == "Existing Admin"
    assert data["admins"][0]["branchName"] == env["branch"].name
    assert len(data["branches"]) == 2


def test_invite_admin_creates_branch_admin(env):
    resp = _client(env["super_admin"]).post(reverse("accounts:admins"), {
        "name": "Neha Singh", "phone": "+919765432120", "branchId": str(env["branch"].id),
    }, format="json")
    assert resp.status_code == 201, resp.content
    admin = resp.json()["data"]["admin"]
    assert admin["name"] == "Neha Singh"
    assert admin["branchId"] == str(env["branch"].id)
    assert User.objects.filter(phone="+919765432120", role=Role.ADMIN).exists()


def test_set_admin_inactive(env):
    resp = _client(env["super_admin"]).patch(
        reverse("accounts:admin-detail", kwargs={"admin_id": str(env["admin"].id)}),
        {"isActive": False}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["data"]["admin"]["isActive"] is False
    env["admin"].refresh_from_db()
    assert env["admin"].is_active is False


def test_reassign_admin_branch(env):
    resp = _client(env["super_admin"]).patch(
        reverse("accounts:admin-detail", kwargs={"admin_id": str(env["admin"].id)}),
        {"branchId": str(env["branch2"].id)}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["data"]["admin"]["branchId"] == str(env["branch2"].id)


def test_non_super_admin_denied(env):
    resp = _client(env["admin"]).get(reverse("accounts:admins"))
    assert resp.status_code == 403
