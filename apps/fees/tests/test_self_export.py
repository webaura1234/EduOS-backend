"""Request-level tests for the student fee-statement self-service export,
and the FeeDefaultersExport definition (refactored from the legacy
ADMISSION_FUNNEL-style row resolver into the unified export framework)."""

import datetime

import pytest
from django.urls import reverse

from apps.analytics.enums import ReportStatus, ReportType
from apps.analytics.interactors import report as report_i
from apps.fees.enums import InvoiceStatus
from apps.fees.models import FeeInvoice

pytestmark = pytest.mark.django_db


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def test_student_can_export_own_fee_statement(student_client, student_profile, branch):
    FeeInvoice.objects.create(branch=branch, student=student_profile.enrollment, total_paise=10000, paid_paise=5000)
    FeeInvoice.objects.create(branch=branch, student=student_profile.enrollment, total_paise=20000, paid_paise=20000)

    resp = student_client.post(reverse("fees:student-export-fee-statement"), {}, format="json")
    assert resp.status_code == 201, resp.content
    report = _data(resp)["report"]
    assert report["reportType"] == "student_fee_statement"
    assert report["status"] == ReportStatus.READY
    assert report["rowCount"] == 2


def test_student_cannot_see_another_students_invoices(
    student_client, student_profile, branch, tenant,
):
    from apps.accounts.models.profile import AcademicStatus, StudentProfile
    from apps.accounts.models.user import Role
    from apps.accounts.tests.factories import UserFactory
    from apps.admissions.queries.enrollment import resolve_enrollment_for_profile

    other_user = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                             custom_login_id="STU-999", must_change_password=False)
    other_profile = StudentProfile.objects.create(
        user=other_user, current_batch=student_profile.current_batch,
        academic_status=AcademicStatus.ACTIVE,
    )
    other_enrollment = resolve_enrollment_for_profile(other_profile)

    FeeInvoice.objects.create(branch=branch, student=student_profile.enrollment, total_paise=10000, paid_paise=0)
    FeeInvoice.objects.create(branch=branch, student=other_enrollment, total_paise=99999, paid_paise=0)

    resp = student_client.post(reverse("fees:student-export-fee-statement"), {}, format="json")
    report = _data(resp)["report"]
    assert report["rowCount"] == 1
    assert report["snapshot"]["rows"][0]["amount"] == 100.0


def test_admin_cannot_use_student_fee_statement_endpoint(admin_client):
    resp = admin_client.post(reverse("fees:student-export-fee-statement"), {}, format="json")
    assert resp.status_code == 403


def test_fee_defaulters_export_only_past_due_unpaid_invoices(tenant, branch, admin, student_profile):
    past_due = datetime.date.today() - datetime.timedelta(days=5)
    future_due = datetime.date.today() + datetime.timedelta(days=5)

    # Past due + unpaid → should appear
    FeeInvoice.objects.create(branch=branch, student=student_profile.enrollment,
                              total_paise=50000, paid_paise=0, due_date=past_due, status=InvoiceStatus.DUE)
    # Past due but fully paid → must NOT appear
    FeeInvoice.objects.create(branch=branch, student=student_profile.enrollment,
                              total_paise=50000, paid_paise=50000, due_date=past_due, status=InvoiceStatus.PAID)
    # Not yet due → must NOT appear
    FeeInvoice.objects.create(branch=branch, student=student_profile.enrollment,
                              total_paise=50000, paid_paise=0, due_date=future_due, status=InvoiceStatus.DUE)

    export = report_i.generate_report(
        tenant=tenant, branch=branch, report_type=ReportType.FEE_DEFAULTERS,
        params={}, requester=admin,
    )
    assert export.status == ReportStatus.READY
    assert export.row_count == 1
    assert export.snapshot["rows"][0]["balance"] == 500.0
