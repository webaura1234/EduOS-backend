"""Faculty account Profile tab — view form, edit name/ownPhone, change password."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.profile import FacultyProfile
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
    user = UserFactory(
        role=Role.FACULTY,
        tenant=tenant,
        branch=branch,
        custom_login_id="FAC-001",
        first_name="Kavitha",
        last_name="Rao",
        must_change_password=False,
    )
    user.set_password("Password123!")
    user.save()
    FacultyProfile.objects.create(
        user=user,
        designation="Senior Teacher",
        department="Mathematics",
    )
    return dict(user=user)


def test_get_profile_form(env):
    body = _data(_client(env["user"]).get(reverse("accounts:faculty-profile-form")))
    assert body["name"] == "Kavitha Rao"
    assert body["customLoginId"] == "FAC-001"
    assert body["designation"] == "Senior Teacher"
    assert body["department"] == "Mathematics"
    assert body["editableFields"] == ["name", "ownPhone"]


def test_update_name_and_own_phone(env):
    url = reverse("accounts:faculty-profile-form")
    resp = _client(env["user"]).patch(
        url,
        {"name": "Kavitha K Rao", "ownPhone": "+919999999999"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    p = _data(resp)["profile"]
    assert p["name"] == "Kavitha K Rao"
    assert p["ownPhone"] == "+919999999999"
    env["user"].refresh_from_db()
    assert env["user"].phone == "+919999999999"


def test_change_password(env):
    url = reverse("accounts:faculty-profile-form")
    c = _client(env["user"])
    bad = c.post(
        url,
        {"currentPassword": "wrong", "newPassword": "NewPass123!"},
        format="json",
    )
    assert bad.status_code == 400
    ok = c.post(
        url,
        {"currentPassword": "Password123!", "newPassword": "NewPass123!"},
        format="json",
    )
    assert ok.status_code == 200
    env["user"].refresh_from_db()
    assert env["user"].check_password("NewPass123!")
