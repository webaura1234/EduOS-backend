"""API tests for the ID-format settings endpoint + end-to-end generation."""

import pytest
from rest_framework.test import APIClient

from apps.accounts.id_generation import generate_user_id
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db

URL = "/api/v1/organizations/id-format-settings/"


def _super_admin_client():
    tenant = TenantFactory()
    branch = BranchFactory(tenant=tenant, code="ABCS")
    admin = UserFactory(tenant=tenant, branch=branch, role=Role.SUPER_ADMIN)
    client = APIClient()
    client.force_authenticate(user=admin)
    return client, branch


def test_get_returns_defaults():
    client, _ = _super_admin_client()
    res = client.get(URL)
    assert res.status_code == 200
    assert res.data["studentIdFormat"] == "{BRANCH}/{YEAR}/{SEQ}"
    assert res.data["facultyIdSeqWidth"] == 4


def test_patch_updates_and_affects_generation():
    client, branch = _super_admin_client()
    res = client.patch(
        URL,
        {"studentIdFormat": "ADM-{YY}-{SEQ}", "studentIdSeqWidth": 3},
        format="json",
    )
    assert res.status_code == 200
    assert res.data["studentIdFormat"] == "ADM-{YY}-{SEQ}"

    generated = generate_user_id(branch, Role.STUDENT, "2025-2026")
    assert generated == "ADM-25-001"


def test_patch_rejects_format_without_seq_token():
    client, _ = _super_admin_client()
    res = client.patch(URL, {"studentIdFormat": "{BRANCH}/{YEAR}"}, format="json")
    assert res.status_code == 400


def test_non_super_admin_forbidden():
    tenant = TenantFactory()
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(tenant=tenant, branch=branch, role=Role.ADMIN)
    client = APIClient()
    client.force_authenticate(user=admin)
    assert client.get(URL).status_code == 403
