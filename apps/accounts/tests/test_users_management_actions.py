"""Admin user-management write actions."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.token import InviteToken
from apps.accounts.models.user import Role, User
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
                          custom_login_id="STU-1", email="kid@example.com",
                          must_change_password=False)
    return dict(tenant=tenant, branch=branch, admin=admin, student=student)


def _act(env, payload):
    return _client(env["admin"]).post(
        reverse("accounts:users-management-actions"), payload, format="json",
    )


def test_deactivate_then_activate(env):
    resp = _act(env, {"action": "deactivate", "userId": str(env["student"].id)})
    assert resp.status_code == 200, resp.content
    assert _data(resp)["is_active"] is False
    env["student"].refresh_from_db()
    assert env["student"].is_active is False

    resp = _act(env, {"action": "activate", "userId": str(env["student"].id)})
    assert _data(resp)["is_active"] is True


def test_send_invite_creates_token(env):
    resp = _act(env, {"action": "send_invite", "userId": str(env["student"].id)})
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert body["user_id"] == str(env["student"].id)
    assert InviteToken.objects.filter(user=env["student"], is_used=False).count() == 1


def test_reset_password_returns_temp(env):
    resp = _act(env, {"action": "reset_password", "userId": str(env["student"].id)})
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert body["temporary_password"]
    assert body["user"]["password_reset_required"] is True


def test_hard_delete_student_no_dues(env):
    sid = str(env["student"].id)
    resp = _act(env, {"action": "hard_delete_student", "userId": sid})
    assert resp.status_code == 200, resp.content
    assert _data(resp)["id"] == sid
    assert not User.objects.filter(pk=sid).exists()


def test_hard_delete_blocked_by_dues(env):
    from apps.accounts.models.profile import StudentProfile
    from apps.admissions.tests.factories import StudentEnrollmentFactory
    from apps.fees.models.invoice import FeeInvoice

    profile = StudentProfile.objects.create(user=env["student"])
    enrollment = StudentEnrollmentFactory(student_profile=profile, branch=env["branch"])
    FeeInvoice.objects.create(branch=env["branch"], student=enrollment,
                              total_paise=500000, paid_paise=0)

    resp = _act(env, {"action": "hard_delete_student", "userId": str(env["student"].id)})
    assert resp.status_code == 400
    assert "open_fee_dues" in resp.content.decode()
    assert User.objects.filter(pk=env["student"].id).exists()


def test_promote_student_to_faculty(env):
    resp = _act(env, {"action": "promote_student_to_faculty",
                      "userId": str(env["student"].id)})
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert body["student"]["role"] == "student"
    assert body["faculty"]["role"] == "faculty"
    assert body["student"]["linked_user_group_id"] == body["faculty"]["linked_user_group_id"]


def test_create_user_with_invite(env):
    resp = _client(env["admin"]).post(
        reverse("accounts:users-management"),
        {"name": "Asha Rao", "email": "asha@example.com", "phone": "+919812345678",
         "role": "parent", "send_invite": True},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = _data(resp)
    assert body["user"]["name"] == "Asha Rao"
    assert body["user"]["role"] == "parent"
    assert body["invite"] is not None


def test_check_multi_role_detects_existing(env):
    # Same phone as the student, but creating a parent → should warn.
    env["student"].phone = "+919812000000"
    env["student"].save(update_fields=["phone"])
    resp = _client(env["admin"]).post(
        reverse("accounts:users-check-multi-role"),
        {"phone": "+919812000000", "email": "", "role": "parent"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    warning = _data(resp)["warning"]
    assert warning is not None
    assert warning["will_link_by"] == "phone"
    assert any(a["user_id"] == str(env["student"].id) for a in warning["existing_accounts"])
