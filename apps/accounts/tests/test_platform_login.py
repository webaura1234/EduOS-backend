"""Platform-owner login — tenant-less phone+password (separate platform app)."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def platform_owner():
    return UserFactory(role=Role.PLATFORM_OWNER, tenant=None, branch=None,
                       phone="+919800000777", custom_login_id=None,
                       must_change_password=False, password="Owner123!")


def test_platform_login_succeeds(platform_owner):
    resp = APIClient().post(reverse("accounts:platform-login"),
                            {"identifier": "+919800000777", "password": "Owner123!"},
                            format="json")
    assert resp.status_code == 200, resp.content
    data = resp.json()["data"]
    assert data["access"] and data["refresh"]
    assert data["role"] == Role.PLATFORM_OWNER


def test_platform_login_wrong_password(platform_owner):
    resp = APIClient().post(reverse("accounts:platform-login"),
                            {"identifier": "+919800000777", "password": "nope"},
                            format="json")
    assert resp.status_code == 401


def test_platform_login_unknown_phone():
    resp = APIClient().post(reverse("accounts:platform-login"),
                            {"identifier": "+919800000000", "password": "x"},
                            format="json")
    assert resp.status_code == 401
