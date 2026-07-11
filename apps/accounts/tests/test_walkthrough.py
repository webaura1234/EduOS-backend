"""Walkthrough completion — one-time product tour persistence."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models import WalkthroughCompletion
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db

URL = reverse("accounts:me-walkthroughs")


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


@pytest.fixture
def admin_user():
    tenant = TenantFactory()
    branch = BranchFactory(tenant=tenant)
    return UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919810000099",
        custom_login_id=None,
        must_change_password=False,
    )


def test_get_empty_for_new_user(admin_user):
    resp = _client(admin_user).get(URL)
    assert resp.status_code == 200
    assert _data(resp)["completed"] == []


def test_post_persists_key(admin_user):
    key = "dashboard:admin"
    resp = _client(admin_user).post(URL, {"key": key}, format="json")
    assert resp.status_code == 200
    data = _data(resp)
    assert key in data["completed"]
    assert WalkthroughCompletion.objects.filter(user=admin_user, key=key).count() == 1


def test_post_same_key_is_idempotent(admin_user):
    key = "dashboard:admin"
    client = _client(admin_user)
    assert client.post(URL, {"key": key}, format="json").status_code == 200
    assert client.post(URL, {"key": key}, format="json").status_code == 200
    assert WalkthroughCompletion.objects.filter(user=admin_user, key=key).count() == 1


def test_get_returns_persisted_keys(admin_user):
    key = "dashboard:admin"
    _client(admin_user).post(URL, {"key": key}, format="json")
    data = _data(_client(admin_user).get(URL))
    assert key in data["completed"]


def test_post_invalid_payload_returns_400(admin_user):
    resp = _client(admin_user).post(URL, {}, format="json")
    assert resp.status_code == 400


def test_unauthenticated_returns_401():
    resp = APIClient().get(URL)
    assert resp.status_code == 401
