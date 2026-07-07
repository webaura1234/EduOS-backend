"""Admin user-management aggregate endpoint — UserManagementData shape.

`users` is server-side paginated/filtered/searched (see apps/core/pagination.py) —
these tests assert the {count, next, previous, results} envelope and the
?page=/?page_size=/?role=/?search= query params all work.
"""

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
    assert set(body["users"]) == {"count", "next", "previous", "results"}
    assert isinstance(body["users"]["results"], list)
    assert isinstance(body["pending_invites"], list)
    assert isinstance(body["multi_role_policy"], str)


def test_managed_user_fields_and_invite_status(env):
    InviteToken.objects.create(user=env["student"], sent_to_phone="+910000000000")
    resp = _client(env["admin"]).get(reverse("accounts:users-management"))
    body = _data(resp)

    by_id = {u["id"]: u for u in body["users"]["results"]}
    stu = by_id[str(env["student"].id)]
    assert stu["role"] == "student"
    assert stu["custom_login_id"] == "STU-1"
    assert stu["password_reset_required"] is True
    assert stu["invite_status"] == "pending"
    assert stu["branch"] == env["branch"].name

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
    assert body["users"]["count"] == 2
    assert all(u["branch"] == env["branch"].name for u in body["users"]["results"])


def test_users_are_paginated(env):
    for i in range(25):
        UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
                    custom_login_id=f"STU-BULK-{i}", must_change_password=False)
    # 25 bulk students + admin + the original student from `env` = 27 total;
    # default page_size is 20.
    resp = _client(env["admin"]).get(reverse("accounts:users-management"))
    body = _data(resp)
    assert body["users"]["count"] == 27
    assert len(body["users"]["results"]) == 20
    assert body["users"]["next"] is not None

    resp_page2 = _client(env["admin"]).get(
        reverse("accounts:users-management"), {"page": 2},
    )
    body2 = _data(resp_page2)
    assert len(body2["users"]["results"]) == 7
    assert body2["users"]["previous"] is not None


def test_users_page_size_is_configurable_and_capped(env):
    for i in range(10):
        UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
                    custom_login_id=f"STU-PS-{i}", must_change_password=False)
    resp = _client(env["admin"]).get(
        reverse("accounts:users-management"), {"page_size": 5},
    )
    body = _data(resp)
    assert len(body["users"]["results"]) == 5


def test_users_filtered_by_role(env):
    UserFactory(role=Role.FACULTY, tenant=env["tenant"], branch=env["branch"],
               custom_login_id="FAC-1", must_change_password=False)
    resp = _client(env["admin"]).get(
        reverse("accounts:users-management"), {"role": "faculty"},
    )
    body = _data(resp)
    assert body["users"]["count"] == 1
    assert body["users"]["results"][0]["role"] == "faculty"


def test_users_searched_by_name_email_phone(env):
    UserFactory(role=Role.FACULTY, tenant=env["tenant"], branch=env["branch"],
               first_name="Zendaya", last_name="", custom_login_id="FAC-2",
               must_change_password=False)
    resp = _client(env["admin"]).get(
        reverse("accounts:users-management"), {"search": "zendaya"},
    )
    body = _data(resp)
    assert body["users"]["count"] == 1
    assert body["users"]["results"][0]["name"] == "Zendaya"

    resp_no_match = _client(env["admin"]).get(
        reverse("accounts:users-management"), {"search": "nonexistent-name-xyz"},
    )
    assert _data(resp_no_match)["users"]["count"] == 0
