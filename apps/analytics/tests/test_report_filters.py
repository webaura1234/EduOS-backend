"""Report filter validation, status select, and super-admin branchId (2.1–2.3)."""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.admissions.models import StudentEnrollment
from apps.analytics.enums import ReportType
from apps.analytics.interactors import report as report_i
from apps.core.exports.registry import get_definition
from apps.core.exports.runner import request_export
from apps.fees.enums import InvoiceStatus
from apps.fees.models import FeeInvoice
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
    today = timezone.localdate()
    year = AcademicYearFactory(
        branch=branch,
        name="Current",
        is_current=True,
        start_date=today - datetime.timedelta(days=180),
        end_date=today + datetime.timedelta(days=180),
    )
    admin = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919850000001",
        custom_login_id=None, must_change_password=False,
    )
    super_admin = UserFactory(
        role=Role.SUPER_ADMIN, tenant=tenant, branch=branch, phone="+919850000002",
        custom_login_id=None, must_change_password=False,
    )
    return dict(
        tenant=tenant, branch=branch, year=year, admin=admin, super_admin=super_admin,
    )


def _enrollment(env, *, login_id, batch=None):
    batch = batch or BatchFactory(
        course__department__branch=env["branch"], academic_year=env["year"],
    )
    student = UserFactory(
        role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
        custom_login_id=login_id, must_change_password=False,
    )
    profile = StudentProfile.objects.create(
        user=student, current_batch=batch, academic_status=AcademicStatus.ACTIVE,
    )
    return StudentEnrollment.objects.create(
        branch=env["branch"], student_profile=profile, batch=batch, academic_year=env["year"],
    ), batch


def test_fee_ledger_invalid_status_returns_400(env):
    with pytest.raises(ValidationError) as exc:
        request_export(
            get_definition(ReportType.FEE_LEDGER),
            tenant=env["tenant"],
            branch=env["branch"],
            params={"academicYearId": str(env["year"].pk), "status": "not-a-status"},
            requested_by=env["admin"],
        )
    assert "status" in exc.value.detail


def test_fee_ledger_valid_status_and_batch_filters(env):
    enr, batch = _enrollment(env, login_id="STU-FLT")
    FeeInvoice.objects.create(
        branch=env["branch"], student=enr,
        total_paise=10000, paid_paise=0, status=InvoiceStatus.DUE,
    )
    FeeInvoice.objects.create(
        branch=env["branch"], student=enr,
        total_paise=20000, paid_paise=20000, status=InvoiceStatus.PAID,
    )
    export = report_i.generate_report(
        tenant=env["tenant"],
        branch=env["branch"],
        report_type=ReportType.FEE_LEDGER,
        params={
            "academicYearId": str(env["year"].pk),
            "status": InvoiceStatus.DUE,
            "batchId": str(batch.pk),
        },
        requester=env["admin"],
        threshold=10_000,
    )
    assert export.row_count == 1


def test_attendance_monthly_missing_month_returns_400(env):
    with pytest.raises(ValidationError) as exc:
        request_export(
            get_definition(ReportType.ATTENDANCE_MONTHLY),
            tenant=env["tenant"],
            branch=env["branch"],
            params={"academicYearId": str(env["year"].pk), "year": 2026},
            requested_by=env["admin"],
        )
    assert "month" in exc.value.detail


def test_catalog_fee_ledger_status_is_select_with_options(env):
    resp = _client(env["admin"]).get(reverse("analytics:report-catalog"))
    assert resp.status_code == 200
    body = _data(resp)
    fee_ledger = next(r for r in body["reports"] if r["id"] == ReportType.FEE_LEDGER)
    status_f = next(f for f in fee_ledger["filters"] if f["key"] == "status")
    assert status_f["type"] == "select"
    assert status_f["options"]
    values = {o["value"] for o in status_f["options"]}
    assert InvoiceStatus.DUE in values
    assert any(f["key"] == "batchId" for f in fee_ledger["filters"])


def test_super_admin_branch_id_other_tenant_404(env):
    other = BranchFactory(tenant=TenantFactory(institution_type="school"))
    resp = _client(env["super_admin"]).post(
        reverse("analytics:report-exports"),
        {
            "reportType": ReportType.FEE_COLLECTION,
            "branchId": str(other.pk),
            "params": {"academicYearId": str(env["year"].pk)},
        },
        format="json",
    )
    assert resp.status_code == 404


def test_super_admin_branch_id_own_tenant_ok(env):
    other_branch = BranchFactory(tenant=env["tenant"])
    year_b = AcademicYearFactory(
        branch=other_branch, name="OB-Y", is_current=True,
        start_date=env["year"].start_date, end_date=env["year"].end_date,
    )
    resp = _client(env["super_admin"]).post(
        reverse("analytics:report-exports"),
        {
            "reportType": ReportType.FEE_COLLECTION,
            "branchId": str(other_branch.pk),
            "params": {"academicYearId": str(year_b.pk)},
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    report = _data(resp)["report"]
    assert report["reportType"] == ReportType.FEE_COLLECTION


def test_catalog_super_admin_includes_branches(env):
    BranchFactory(tenant=env["tenant"])
    resp = _client(env["super_admin"]).get(reverse("analytics:report-catalog"))
    assert resp.status_code == 200
    body = _data(resp)
    assert len(body.get("branches") or []) >= 2
