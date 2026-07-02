"""Auth contract tests — lock the exact wire shapes the Next.js BFF consumes.

These assert the RENDERED JSON envelope (response.json()), not the DTO, because the
frontend's `auth-server.ts` reads `envelope.data.<field>`. If a serializer drifts, these
fail — which is the Phase-0 integration guard against FE/BE contract drift.

FE consumers (apps/institution/src/lib/services/auth-server.ts):
  - djangoFetch unwraps `{ success, data, message }`
  - mapMeToAuthUser reads me.data.{id, full_name, role, phone, email, branch_id,
                                    custom_login_id, institution_type, tenant_subdomain,
                                    linked_user_group_id}
  - Admin login → mfa_required shape (isMFARequired check)
  - MFA verify  → access/refresh tokens
  - Student/faculty login → access/refresh tokens directly
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.interactors.mfa import MFAToken
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token, generate_refresh_token

pytestmark = pytest.mark.django_db


def _login(api_client, *, identifier, password, role, tenant_id):
    return api_client.post(
        reverse("accounts:login"),
        {"identifier": identifier, "password": password, "role": role, "tenant_id": str(tenant_id)},
        format="json",
    )


# ── Admin / Super Admin — MFA required ───────────────────────────────────────

def test_admin_login_returns_mfa_required(api_client, tenant, branch):
    """Admin login must return mfa_required shape (not tokens) — isMFARequired() check."""
    UserFactory(role=Role.ADMIN, phone="+919800000111", password="Password123!",
                email="admin@school.in",
                tenant=tenant, branch=branch, custom_login_id=None, must_change_password=False)
    resp = _login(api_client, identifier="+919800000111", password="Password123!",
                  role=Role.ADMIN, tenant_id=tenant.id)
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    # Frontend checks: isMFARequired checks data.mfa_required === true
    assert data.get("mfa_required") is True
    assert "mfa_session_token" in data
    assert "email_hint" in data


def test_mfa_verify_envelope_shape(api_client, tenant, branch):
    """MFA verify must return access+refresh tokens — same as normal login success."""
    user = UserFactory(role=Role.ADMIN, phone="+919800000115", password="Password123!",
                       email="mfa@school.in",
                       tenant=tenant, branch=branch, custom_login_id=None, must_change_password=False)
    # Trigger MFA challenge
    login_resp = _login(api_client, identifier="+919800000115", password="Password123!",
                        role=Role.ADMIN, tenant_id=tenant.id)
    mfa_token = login_resp.json()["data"]["mfa_session_token"]

    # Grab the OTP from the MFAToken table (email is mocked, so it was stored)
    from apps.accounts.interactors.mfa import _hash_otp
    import hashlib
    mfa_record = MFAToken.objects.filter(user=user, is_used=False).latest("created_at")
    # We can't reverse the hash, so we need to find the OTP — bypass by patching verify
    # Instead, test the endpoint with a direct token pair obtained via the MFA interactor
    from apps.accounts.interactors.mfa import verify_mfa_otp
    from apps.accounts.tokens import generate_mfa_session_token
    import secrets
    otp = str(secrets.randbelow(900000) + 100000)
    otp_hash = hashlib.sha256(otp.encode()).hexdigest()
    mfa_record.otp_hash = otp_hash
    mfa_record.save(update_fields=["otp_hash"])
    mfa_session = generate_mfa_session_token(user)

    resp = api_client.post(
        reverse("accounts:mfa-verify"),
        {"mfa_session_token": mfa_session, "otp": otp},
        format="json",
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    for field in ("access", "refresh", "must_change_password", "user_id", "role"):
        assert field in data, f"mfa-verify.data missing '{field}'"
    assert data["role"] == Role.ADMIN


# ── Student / Faculty — direct token login (no MFA) ──────────────────────────

def test_student_login_envelope_shape(api_client, tenant, branch):
    """Student login must return tokens directly (no MFA)."""
    UserFactory(role=Role.STUDENT, custom_login_id="STU-111", password="Pass123!",
                tenant=tenant, branch=branch, must_change_password=False)
    resp = _login(api_client, identifier="STU-111", password="Pass123!",
                  role=Role.STUDENT, tenant_id=tenant.id)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    for field in ("access", "refresh", "must_change_password", "user_id", "role"):
        assert field in data, f"student login.data missing '{field}'"
    # Crucially no mfa_required in the response
    assert "mfa_required" not in data
    assert data["role"] == Role.STUDENT


def test_faculty_login_envelope_shape(api_client, tenant, branch):
    """Faculty login must return tokens directly (no MFA)."""
    UserFactory(role=Role.FACULTY, custom_login_id="FAC-888", password="Pass123!",
                tenant=tenant, branch=branch, must_change_password=False)
    resp = _login(api_client, identifier="FAC-888", password="Pass123!",
                  role=Role.FACULTY, tenant_id=tenant.id)
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    assert data.get("mfa_required") is not True
    assert "access" in data and "refresh" in data


# ── /me/ endpoint ─────────────────────────────────────────────────────────────

def test_me_envelope_shape(api_client, tenant, branch):
    """MeView must return all fields mapMeToAuthUser() reads, incl. new ones."""
    user = UserFactory(role=Role.STUDENT, custom_login_id="STU-999", email="s@school.in",
                       tenant=tenant, branch=branch, must_change_password=False)
    token = generate_access_token(user)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    resp = c.get(reverse("accounts:me"))
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    # Fields read by mapMeToAuthUser() in auth-server.ts
    for field in ("id", "full_name", "role", "phone", "email", "branch_id", "tenant_id",
                  "custom_login_id", "institution_type", "tenant_subdomain", "linked_user_group_id"):
        assert field in data, f"me.data missing '{field}'"
    assert data["id"] == str(user.id)
    assert data["custom_login_id"] == "STU-999"
    assert data["institution_type"] == tenant.institution_type
    assert data["tenant_subdomain"] == tenant.subdomain


# ── Refresh token ─────────────────────────────────────────────────────────────

def test_refresh_envelope_shape(api_client, tenant, branch):
    """Refresh endpoint must return new access+refresh pair."""
    user = UserFactory(role=Role.STUDENT, custom_login_id="STU-777", password="Pass123!",
                       tenant=tenant, branch=branch, must_change_password=False)
    _, db_token = generate_refresh_token(user, device_info="test", ip_address="127.0.0.1")
    resp = api_client.post(reverse("accounts:refresh"), {"refresh": db_token.token}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    assert "access" in data and "refresh" in data


# ── Error shape ───────────────────────────────────────────────────────────────

def test_invalid_login_error_envelope(api_client, tenant, branch):
    """Wrong password must return a standard error envelope."""
    UserFactory(role=Role.STUDENT, custom_login_id="STU-BAD", password="Password123!",
                tenant=tenant, branch=branch)
    resp = _login(api_client, identifier="STU-BAD", password="WrongPass!",
                  role=Role.STUDENT, tenant_id=tenant.id)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    body = resp.json()
    assert body["success"] is False
    assert "message" in body and body["data"] is None


# ── Tenant config ─────────────────────────────────────────────────────────────

def test_tenant_config_envelope_shape(api_client, tenant):
    resp = api_client.get(reverse("organizations:tenant-config"), {"subdomain": tenant.subdomain})
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    for field in ("tenant_id", "institution_type", "subdomain", "student_id_label",
                  "faculty_id_label", "website"):
        assert field in data, f"tenant-config.data missing '{field}'"
    assert data["tenant_id"] == str(tenant.id)
