"""Admin user-management aggregate endpoint — UserManagementData shape."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.token import InviteToken
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch,
                        phone="+919810000001", custom_login_id=None,
                        must_change_password=False)
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                          custom_login_id="STU-1", must_change_password=True)
    return dict(tenant=tenant, branch=branch, admin=admin, student=student)


def test_returns_management_shape(env):
    resp = _client(env["admin"]).get(reverse("accounts:users-management"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert set(body) >= {"users", "pending_invites", "multi_role_policy", "branchId", "branchName"}
    assert isinstance(body["users"], list)
    assert isinstance(body["pending_invites"], list)
    assert isinstance(body["multi_role_policy"], str)


def test_managed_user_fields_and_invite_status(env):
    InviteToken.objects.create(user=env["student"], sent_to_phone="+910000000000")
    resp = _client(env["admin"]).get(reverse("accounts:users-management"))
    body = _data(resp)

    by_id = {u["id"]: u for u in body["users"]}
    stu = by_id[str(env["student"].id)]
    assert stu["role"] == "student"
    assert stu["custom_login_id"] == "STU-1"
    assert stu["password_reset_required"] is True
    assert stu["invite_status"] == "pending"
    assert stu["branch"] == str(env["branch"].id)

    adm = by_id[str(env["admin"].id)]
    assert adm["invite_status"] == "none"
    assert adm["password_reset_required"] is False

    assert len(body["pending_invites"]) == 1
    inv = body["pending_invites"][0]
    assert inv["user_id"] == str(env["student"].id)
    assert inv["used_at"] is None


def test_requires_admin(env):
    resp = _client(env["student"]).get(reverse("accounts:users-management"))
    assert resp.status_code == 403


def test_overview_scoped_to_admin_branch(env):
    branch_b = BranchFactory(tenant=env["tenant"], name="North campus")
    UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=branch_b,
                custom_login_id="STU-2", must_change_password=False)
    body = _data(_client(env["admin"]).get(reverse("accounts:users-management")))
    assert body["branchName"] == env["branch"].name
    assert len(body["users"]) == 2
    assert all(u["branch"] == str(env["branch"].id) for u in body["users"])
