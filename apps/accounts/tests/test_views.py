import pytest
from unittest.mock import patch
from django.urls import reverse
from rest_framework import status

from apps.accounts.models.user import Role
from apps.accounts.models.token import OTPRecord, InviteToken, RefreshToken
from apps.accounts.tests.factories import UserFactory, RefreshTokenFactory, OTPRecordFactory, InviteTokenFactory
from apps.accounts.interactors import password as password_interactor


def test_login_view(api_client, tenant, branch):
    user = UserFactory(
        role=Role.STUDENT,
        custom_login_id="S123",
        password="Password123!",
        tenant=tenant,
        branch=branch,
        must_change_password=True,
    )

    url = reverse("accounts:login")
    data = {
        "identifier": "S123",
        "password": "Password123!",
        "role": Role.STUDENT,
        "tenant_id": str(tenant.id),
    }

    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data.access
    assert response.data.refresh
    assert response.data.must_change_password is True
    assert str(response.data.user_id) == str(user.id)


def test_login_view_invalid(api_client, tenant, branch):
    UserFactory(
        role=Role.STUDENT,
        custom_login_id="S123",
        password="Password123!",
        tenant=tenant,
        branch=branch,
    )

    url = reverse("accounts:login")
    data = {
        "identifier": "S123",
        "password": "WrongPassword!",
        "role": Role.STUDENT,
        "tenant_id": str(tenant.id),
    }

    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_refresh_view(api_client):
    rt = RefreshTokenFactory(token="refresh-token-value")
    url = reverse("accounts:refresh")
    data = {
        "refresh": "refresh-token-value",
    }

    # Mock the rotation logic so we don't try to parse 'refresh-token-value' as real JWT in decode
    with patch("apps.accounts.interactors.auth.decode_refresh_token") as mock_decode:
        mock_decode.return_value = {"user_id": str(rt.user.id)}
        response = api_client.post(url, data, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data.access
        assert response.data.refresh


def test_logout_view(admin_auth_client, admin_user):
    rt = RefreshTokenFactory(user=admin_user, token="logout-refresh-token")
    url = reverse("accounts:logout")
    data = {
        "refresh": "logout-refresh-token",
    }

    response = admin_auth_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    rt.refresh_from_db()
    assert rt.is_revoked is True


def test_me_view(admin_auth_client, admin_user):
    url = reverse("accounts:me")
    response = admin_auth_client.get(url)
    assert response.status_code == status.HTTP_200_OK
    assert str(response.data["id"]) == str(admin_user.id)
    assert response.data["role"] == admin_user.role
    # Resolved branch/tenant branding for the authed app (per-branch theming).
    assert "theme" in response.data
    assert response.data["theme"]["primaryColor"].startswith("#")


def test_me_view_unauthenticated(api_client):
    url = reverse("accounts:me")
    response = api_client.get(url)
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_force_change_password_view(auth_client, student_user):
    url = reverse("accounts:password-change")
    data = {
        "current_password": "TestPass123!",
        "new_password": "NewSecurePassword123!",
        "confirm_password": "NewSecurePassword123!",
    }

    response = auth_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    student_user.refresh_from_db()
    assert student_user.must_change_password is False
    assert student_user.check_password("NewSecurePassword123!") is True


@patch("apps.accounts.interactors.password._send_otp")
def test_otp_request_view(mock_send, api_client, tenant, branch):
    UserFactory(
        role=Role.ADMIN,
        phone="+919876543210",
        tenant=tenant,
        branch=branch,
    )
    url = reverse("accounts:otp-request")
    data = {
        "phone": "+919876543210",
        "tenant_id": str(tenant.id),
    }

    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert mock_send.called


def test_otp_verify_view(api_client, tenant, branch):
    phone = "+919876543210"
    user = UserFactory(
        role=Role.ADMIN,
        phone=phone,
        tenant=tenant,
        branch=branch,
    )
    otp_hash = password_interactor._hash_otp("123456")
    OTPRecordFactory(user=user, phone=phone, otp_hash=otp_hash)

    url = reverse("accounts:otp-verify")
    data = {
        "phone": phone,
        "otp": "123456",
        "new_password": "NewSecurePassword123!",
        "confirm_password": "NewSecurePassword123!",
        "tenant_id": str(tenant.id),
    }

    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    user.refresh_from_db()
    assert user.check_password("NewSecurePassword123!") is True


def test_create_invite_view(admin_auth_client, tenant, branch):
    url = reverse("accounts:invite-create")
    data = {
        "role": Role.FACULTY,
        "first_name": "Ramesh",
        "custom_login_id": "EMP555",
    }

    response = admin_auth_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_201_CREATED
    assert response.data.user_id
    assert response.data.invite_token


def test_accept_invite_view(api_client, tenant, branch):
    student = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        must_change_password=True,
    )
    student.set_unusable_password()
    student.save()

    invite = InviteTokenFactory(user=student)

    url = reverse("accounts:invite-accept")
    data = {
        "token": str(invite.token),
        "new_password": "NewSecurePassword123!",
        "confirm_password": "NewSecurePassword123!",
    }

    response = api_client.post(url, data, format="json")
    assert response.status_code == status.HTTP_200_OK
    assert response.data.access
    assert response.data.refresh
    student.refresh_from_db()
    assert student.must_change_password is False
    assert student.check_password("NewSecurePassword123!") is True
