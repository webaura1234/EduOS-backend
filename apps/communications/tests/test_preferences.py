"""Per-user notification preferences (F-179)."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


@pytest.fixture
def faculty():
    tenant = TenantFactory(institution_type="college")
    branch = BranchFactory(tenant=tenant)
    return UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                       custom_login_id="FAC-1", must_change_password=False)


def test_get_defaults_all_on(faculty):
    resp = _client(faculty).get(reverse("communications:notification-preferences"))
    assert resp.status_code == 200, resp.content
    data = resp.json()["data"]
    assert data["userId"] == str(faculty.id)
    assert data["channels"] == {"in_app": True, "sms": True, "email": True}


def test_patch_toggles_channel(faculty):
    c = _client(faculty)
    resp = c.patch(reverse("communications:notification-preferences"),
                   {"sms": False}, format="json")
    assert resp.status_code == 200, resp.content
    assert resp.json()["data"]["channels"]["sms"] is False
    # Persisted across requests.
    again = c.get(reverse("communications:notification-preferences"))
    assert again.json()["data"]["channels"] == {"in_app": True, "sms": False, "email": True}
