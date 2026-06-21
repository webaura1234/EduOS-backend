"""Tests for linked-accounts + switch-linked (F-223 multi-role account switching).

These complete the auth vertical slice the frontend BFF (auth-server.ts) calls.
"""

import uuid

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
def linked_pair():
    """One person, two roles: a faculty and a parent sharing a linked_user_group_id."""
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    group = uuid.uuid4()
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                          custom_login_id="FAC-1", linked_user_group_id=group,
                          must_change_password=False, password="Secret123!")
    parent = UserFactory(role=Role.PARENT, tenant=tenant, branch=branch,
                         phone="+919811111111", custom_login_id=None,
                         linked_user_group_id=group, must_change_password=False,
                         password="Secret123!")
    return dict(tenant=tenant, branch=branch, faculty=faculty, parent=parent)


def test_linked_accounts_lists_the_other_role(linked_pair):
    resp = _client(linked_pair["faculty"]).get(reverse("accounts:linked-accounts"))
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert len(data) == 1
    assert data[0]["userId"] == str(linked_pair["parent"].id)
    assert data[0]["role"] == Role.PARENT
    assert data[0]["label"]  # human label present


def test_linked_accounts_empty_when_not_linked():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    solo = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, custom_login_id=None,
                       phone="+919822222222", must_change_password=False)
    resp = _client(solo).get(reverse("accounts:linked-accounts"))
    assert resp.status_code == 200
    assert resp.json()["data"] == []


def test_switch_linked_issues_tokens_for_target(linked_pair):
    resp = _client(linked_pair["faculty"]).post(
        reverse("accounts:switch-linked"),
        {"target_user_id": str(linked_pair["parent"].id), "password": "Secret123!"},
        format="json",
    )
    assert resp.status_code == 200, resp.content
    data = resp.json()["data"]
    assert data["access"] and data["refresh"]
    assert data["user"]["id"] == str(linked_pair["parent"].id)
    assert data["user"]["role"] == Role.PARENT
    assert data["user"]["tenant_subdomain"] == linked_pair["tenant"].subdomain


def test_switch_linked_wrong_password_rejected(linked_pair):
    resp = _client(linked_pair["faculty"]).post(
        reverse("accounts:switch-linked"),
        {"target_user_id": str(linked_pair["parent"].id), "password": "WrongPass!"},
        format="json",
    )
    assert resp.status_code in (401, 403)


def test_switch_linked_unlinked_target_rejected(linked_pair):
    """An account not in the caller's linked group cannot be switched to."""
    other = UserFactory(role=Role.STUDENT, tenant=linked_pair["tenant"],
                        branch=linked_pair["branch"], custom_login_id="STU-X",
                        must_change_password=False, password="Secret123!")
    resp = _client(linked_pair["faculty"]).post(
        reverse("accounts:switch-linked"),
        {"target_user_id": str(other.id), "password": "Secret123!"},
        format="json",
    )
    assert resp.status_code in (401, 403)
