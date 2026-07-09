"""Platform-owner passwordless OTP login."""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def platform_owner():
    return UserFactory(
        role=Role.PLATFORM_OWNER,
        tenant=None,
        branch=None,
        phone="+919800000777",
        email="owner@platform.in",
        custom_login_id=None,
        must_change_password=False,
        password="Owner123!",
    )


def test_platform_password_login_rejected(platform_owner):
    """Legacy platform/login rejects password — OTP flow only."""
    resp = APIClient().post(
        reverse("accounts:platform-login"),
        {"identifier": "+919800000777", "password": "Owner123!"},
        format="json",
    )
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


def test_platform_otp_login_request(platform_owner):
    resp = APIClient().post(
        reverse("accounts:otp-login-request"),
        {"phone": "+919800000777"},
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    assert data.get("mfa_required") is True
    assert "mfa_session_token" in data


def test_platform_otp_login_unknown_phone():
    resp = APIClient().post(
        reverse("accounts:otp-login-request"),
        {"phone": "+919800000000"},
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    assert resp.json()["data"].get("password_required") is True
