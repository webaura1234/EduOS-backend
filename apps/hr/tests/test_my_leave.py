"""Faculty-facing my-leave endpoint (balances + own requests + apply)."""

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
    fac_user = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                           custom_login_id="FAC-1", must_change_password=False)
    emp = Employee.objects.create(user=fac_user, branch=branch, employee_code="FAC-1",
                                  employment_type="full_time", joined_at=datetime.date(2024, 1, 1))
    return dict(branch=branch, fac_user=fac_user, emp=emp)


def test_apply_then_list_own_leave(env):
    from apps.fees.helpers.paise import financial_year_for
    from apps.hr.models import LeaveBalance

    LeaveBalance.objects.create(
        employee=env["emp"], leave_type="casual",
        year=financial_year_for(datetime.date(2026, 7, 1)), balance_days=10,
    )
    url = reverse("hr:my-leave")
    c = _client(env["fac_user"])

    resp = c.post(url, {"leaveType": "casual", "fromDate": "2026-07-01",
                        "toDate": "2026-07-02", "reason": "Personal"}, format="json")
    assert resp.status_code == 201, resp.content
    assert _data(resp)["leave"]["leaveType"] == "casual"

    resp = c.get(url)
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert "balances" in body
    assert len(body["requests"]) == 1
    assert body["requests"][0]["reason"] == "Personal"


def test_no_employee_record_empty(env):
    other = UserFactory(role=Role.FACULTY, tenant=env["branch"].tenant, branch=env["branch"],
                        custom_login_id="FAC-X", must_change_password=False)
    resp = _client(other).get(reverse("hr:my-leave"))
    assert resp.status_code == 200, resp.content
    assert _data(resp)["requests"] == []
