"""Faculty payslip — transforms payslips into months + selected month's result."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.hr.models import Employee
from apps.hr.models.payroll import Payslip, PayrollRun
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
    user = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                       custom_login_id="FAC-1", first_name="Asha", must_change_password=False)
    emp = Employee.objects.create(user=user, branch=branch, employee_code="FAC-1",
                                  employment_type="full_time",
                                  joined_at=datetime.date(2024, 1, 1))
    run = PayrollRun.objects.create(branch=branch, period_month=datetime.date(2026, 5, 1),
                                    status="locked")
    slip = Payslip.objects.create(
        payroll_run=run, employee=emp,
        components=[{"name": "Basic", "amountPaise": 5000000}],
        gross_paise=5000000, deductions_paise=600000, net_paise=4400000)
    return dict(branch=branch, user=user, emp=emp, run=run, slip=slip)


def test_payslip_transform_shape(env):
    body = _data(_client(env["user"]).get(reverse("hr:faculty-payslip")))
    assert body["employeeId"] == str(env["emp"].id)
    assert body["employeeName"]  # full name resolved
    assert body["selectedMonth"] == "2026-05"
    assert body["months"][0] == {"month": "2026-05", "label": "May 2026", "status": "processed"}
    result = body["result"]
    assert result["canDownload"] is True
    assert "Net Pay" in result["content"]
    assert result["fileName"] == "payslip-2026-05.txt"


def test_draft_run_blocks_download(env):
    env["run"].status = "running"
    env["run"].save(update_fields=["status"])
    body = _data(_client(env["user"]).get(reverse("hr:faculty-payslip")))
    assert body["months"][0]["status"] == "draft"
    assert body["result"]["canDownload"] is False
    assert body["result"]["content"] == ""


def test_no_employee_record_returns_empty(env):
    other = UserFactory(role=Role.FACULTY, tenant=env["branch"].tenant, branch=env["branch"],
                        custom_login_id="FAC-9", must_change_password=False)
    body = _data(_client(other).get(reverse("hr:faculty-payslip")))
    assert body["employeeId"] is None and body["months"] == [] and body["result"] is None
