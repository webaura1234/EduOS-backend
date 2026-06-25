"""Auth contract tests — lock the exact wire shapes the Next.js BFF consumes.

These assert the RENDERED JSON envelope (response.json()), not the DTO, because the
frontend's `auth-server.ts` reads `envelope.data.<field>`. If a serializer drifts, these
fail — which is the Phase-0 integration guard against FE/BE contract drift.

FE consumers (apps/institution/src/lib/services/auth-server.ts):
  - djangoFetch unwraps `{ success, data, message }`
  - mapMeToAuthUser reads me.data.{id, full_name, role, phone, email, branch_id}
  - login reads data.{access, refresh}; refresh reads data.{access, refresh}
  - tenant-config reads data.{tenant_id, institution_type, ...}
"""

import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def _login(api_client, *, identifier, password, role, tenant_id):
    return api_client.post(
        reverse("accounts:login"),
        {"identifier": identifier, "password": password, "role": role, "tenant_id": str(tenant_id)},
        format="json",
    )


def test_login_envelope_shape(api_client, tenant, branch):
    UserFactory(role=Role.ADMIN, phone="+919800000111", password="Password123!",
                tenant=tenant, branch=branch, custom_login_id=None, must_change_password=False)
    resp = _login(api_client, identifier="+919800000111", password="Password123!",
                  role=Role.ADMIN, tenant_id=tenant.id)
    assert resp.status_code == status.HTTP_200_OK
    body = resp.json()
    # Envelope (StandardJSONRenderer)
    assert body["success"] is True
    data = body["data"]
    # Exact fields the FE reads off the login response.
    for field in ("access", "refresh", "must_change_password", "user_id", "role"):
        assert field in data, f"login.data missing '{field}'"
    assert data["role"] == Role.ADMIN


def test_me_envelope_shape(api_client, tenant, branch):
    user = UserFactory(role=Role.ADMIN, phone="+919800000112", password="Password123!",
                       tenant=tenant, branch=branch, custom_login_id=None,
                       must_change_password=False)
    login = _login(api_client, identifier="+919800000112", password="Password123!",
                   role=Role.ADMIN, tenant_id=tenant.id)
    access = login.json()["data"]["access"]

    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    resp = c.get(reverse("accounts:me"))
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    # Exact fields mapMeToAuthUser() reads.
    for field in ("id", "full_name", "role", "phone", "email", "branch_id", "tenant_id"):
        assert field in data, f"me.data missing '{field}'"
    assert data["id"] == str(user.id)
    assert data["role"] == Role.ADMIN


def test_refresh_envelope_shape(api_client, tenant, branch):
    UserFactory(role=Role.ADMIN, phone="+919800000113", password="Password123!",
                tenant=tenant, branch=branch, custom_login_id=None, must_change_password=False)
    login = _login(api_client, identifier="+919800000113", password="Password123!",
                   role=Role.ADMIN, tenant_id=tenant.id)
    refresh_token = login.json()["data"]["refresh"]

    resp = api_client.post(reverse("accounts:refresh"), {"refresh": refresh_token}, format="json")
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    assert "access" in data and "refresh" in data


def test_invalid_login_error_envelope(api_client, tenant, branch):
    UserFactory(role=Role.ADMIN, phone="+919800000114", password="Password123!",
                tenant=tenant, branch=branch, custom_login_id=None, must_change_password=False)
    resp = _login(api_client, identifier="+919800000114", password="WrongPass!",
                  role=Role.ADMIN, tenant_id=tenant.id)
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED
    body = resp.json()
    # FE error path reads `body.message`.
    assert body["success"] is False
    assert "message" in body and body["data"] is None


def test_tenant_config_envelope_shape(api_client, tenant):
    resp = api_client.get(reverse("organizations:tenant-config"), {"subdomain": tenant.subdomain})
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()["data"]
    # Exact fields the FE login flow reads to resolve tenant_id + login config.
    for field in ("tenant_id", "institution_type", "subdomain", "student_id_label",
                  "faculty_id_label", "website"):
        assert field in data, f"tenant-config.data missing '{field}'"
    assert data["tenant_id"] == str(tenant.id)
