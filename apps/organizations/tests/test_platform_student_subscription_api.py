"""API tests for platform-owner student subscription roster."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.organizations.billing.student_subscription import backfill_student_platform_subscriptions
from apps.organizations.enums import StudentPlatformSubscriptionStatus
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def platform_owner():
    return UserFactory(
        role=Role.PLATFORM_OWNER,
        tenant=None,
        branch=None,
        phone="+919700000099",
        custom_login_id=None,
        must_change_password=False,
    )


@pytest.fixture
def client(platform_owner):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(platform_owner)}")
    return c


def _data(resp):
    return resp.json().get("data", resp.json())


def test_list_student_subscriptions_paginated(client):
    tenant = TenantFactory(subdomain="subs-school")
    branch = BranchFactory(tenant=tenant, name="Main")
    UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-001")
    UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-002")
    backfill_student_platform_subscriptions(tenant_id=tenant.id, paid_fraction=0.5)

    resp = client.get(reverse("organizations:platform-student-subscriptions"), {"pageSize": 1})
    assert resp.status_code == 200
    body = _data(resp)
    assert body["pagination"]["total"] == 2
    assert len(body["rows"]) == 1
    assert body["stats"]["totalStudents"] == 2
    assert "filterOptions" in body


def test_filter_by_tenant_and_mark_paid(client):
    tenant = TenantFactory(subdomain="filter-co")
    branch = BranchFactory(tenant=tenant)
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-X1")
    backfill_student_platform_subscriptions(tenant_id=tenant.id, paid_fraction=0.0)

    list_resp = client.get(
        reverse("organizations:platform-student-subscriptions"),
        {"tenantId": str(tenant.id), "status": "unpaid"},
    )
    row_id = _data(list_resp)["rows"][0]["id"]

    patch_resp = client.patch(
        reverse("organizations:platform-student-subscription-actions"),
        {"studentSubscriptionId": row_id, "action": "mark_paid"},
        format="json",
    )
    assert patch_resp.status_code == 200
    assert _data(patch_resp)["row"]["status"] == StudentPlatformSubscriptionStatus.PAID


def test_forbidden_for_super_admin():
    tenant = TenantFactory()
    super_admin = UserFactory(
        role=Role.SUPER_ADMIN,
        tenant=tenant,
        phone="+919733333344",
        custom_login_id=None,
        must_change_password=False,
    )
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(super_admin)}")
    assert c.get(reverse("organizations:platform-student-subscriptions")).status_code == 403
