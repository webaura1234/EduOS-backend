"""Admin HR overview aggregate endpoint — returns the tenant-wide HrData shape."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.hr.models import Employee
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch,
                        phone="+919810000001", custom_login_id=None,
                        must_change_password=False)
    fac_user = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                           custom_login_id="FAC-1", must_change_password=False)
    emp = Employee.objects.create(
        user=fac_user, branch=branch, employee_code="FAC-1",
        employment_type="full_time", joined_at=datetime.date(2024, 1, 1),
    )
    return dict(tenant=tenant, branch=branch, admin=admin, emp=emp)


def test_overview_returns_all_nine_lists(env):
    resp = _client(env["admin"]).get(reverse("hr:admin-overview"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    for key in ("branches", "branchAdmins", "employees", "assignments",
                "leaveBalances", "leaveRequests", "payrollRuns",
                "componentTemplates", "documents"):
        assert key in body, f"missing {key}"
        assert isinstance(body[key], list)


def test_overview_includes_employee_with_camelcase_fields(env):
    resp = _client(env["admin"]).get(reverse("hr:admin-overview"))
    body = _data(resp)
    assert len(body["employees"]) == 1
    emp = body["employees"][0]
    assert emp["id"] == str(env["emp"].id)
    assert emp["primaryBranchId"] == str(env["branch"].id)
    assert emp["employmentType"] == "full_time"
    assert emp["active"] is True
    assert emp["joinedAt"].startswith("2024-01-01")


def test_overview_requires_admin(env):
    student = UserFactory(role=Role.STUDENT, tenant=env["tenant"],
                          branch=env["branch"], custom_login_id="STU-1",
                          must_change_password=False)
    resp = _client(student).get(reverse("hr:admin-overview"))
    assert resp.status_code == 403
