"""Golden parity tests — verify report output shape before/after framework migration."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.queries.enquiry import create_enquiry
from apps.analytics.enums import ReportStatus, ReportType
from apps.analytics.interactors import report as report_i
from apps.core.exports.registry import get_definition
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919830000001",
        custom_login_id=None, must_change_password=False,
    )
    return dict(tenant=tenant, branch=branch, admin=admin)


def _column_keys(report_type: str) -> list[str]:
    return [c.key for c in get_definition(report_type).get_columns({})]


def test_admission_funnel_columns_and_rows(env):
    create_enquiry(branch=env["branch"], source="walk_in", applicant_name="Asha")
    export = report_i.generate_report(
        tenant=env["tenant"], branch=env["branch"],
        report_type=ReportType.ADMISSION_FUNNEL, params={}, requester=env["admin"],
    )
    assert export.status == ReportStatus.READY
    rows = export.snapshot["rows"]
    assert rows
    assert _column_keys(ReportType.ADMISSION_FUNNEL) == ["dimension", "k", "n"]
    assert "dimension" in rows[0] and "n" in rows[0]


def test_fee_defaulters_registered_definition(env):
    import datetime
    from apps.accounts.models.profile import AcademicStatus, StudentProfile
    from apps.admissions.models import StudentEnrollment
    from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
    from apps.fees.enums import InvoiceStatus
    from apps.fees.models import FeeInvoice

    branch = env["branch"]
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    student = UserFactory(
        role=Role.STUDENT, tenant=env["tenant"], branch=branch,
        custom_login_id="STU-PARITY", must_change_password=False,
    )
    profile = StudentProfile.objects.create(
        user=student, current_batch=batch, academic_status=AcademicStatus.ACTIVE,
    )
    enrollment = StudentEnrollment.objects.create(
        branch=branch, student_profile=profile, batch=batch, academic_year=year,
    )

    past_due = datetime.date.today() - datetime.timedelta(days=5)
    FeeInvoice.objects.create(
        branch=branch, student=enrollment,
        total_paise=50000, paid_paise=0, due_date=past_due, status=InvoiceStatus.DUE,
    )
    export = report_i.generate_report(
        tenant=env["tenant"], branch=branch,
        report_type=ReportType.FEE_DEFAULTERS, params={}, requester=env["admin"],
    )
    assert export.row_count == 1
    keys = _column_keys(ReportType.FEE_DEFAULTERS)
    assert keys == [
        "invoice_id", "student_name", "branch", "structure_name",
        "structure_version", "due_date", "balance",
    ]


def test_hr_leave_summary_columns(env):
    export = report_i.generate_report(
        tenant=env["tenant"], branch=env["branch"],
        report_type=ReportType.HR_LEAVE_SUMMARY, params={}, requester=env["admin"],
    )
    assert export.status == ReportStatus.READY
    assert _column_keys(ReportType.HR_LEAVE_SUMMARY) == [
        "leave_type", "status", "n", "days",
    ]


def test_hr_headcount_export(env):
    export = report_i.generate_report(
        tenant=env["tenant"], branch=env["branch"],
        report_type=ReportType.HR_HEADCOUNT, params={}, requester=env["admin"],
    )
    assert export.status == ReportStatus.READY
    assert _column_keys(ReportType.HR_HEADCOUNT)[0] == "employeeCode"


def test_fee_collection_export(env):
    export = report_i.generate_report(
        tenant=env["tenant"], branch=env["branch"],
        report_type=ReportType.FEE_COLLECTION, params={}, requester=env["admin"],
    )
    assert export.status == ReportStatus.READY
    assert "batchName" in _column_keys(ReportType.FEE_COLLECTION)


def test_catalog_lists_registered_reports(env):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(env['admin'])}")
    resp = client.get(reverse("analytics:report-catalog"))
    assert resp.status_code == 200
    body = resp.json().get("data", resp.json())
    ids = {r["id"] for r in body["reports"]}
    assert ReportType.FEE_LEDGER in ids
    assert ReportType.ADMISSION_FUNNEL in ids
    assert ReportType.ATTENDANCE_DETENTION in ids
    assert ReportType.FEE_COLLECTION in ids
