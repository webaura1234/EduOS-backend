"""End-to-end tests for exam registration and hall tickets (Stage 4.2)."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import AcademicPeriod, AcademicYear, Batch, Course, Department
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.fees.queries.invoice import apply_amount_to_invoice, get_invoice_by_id
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
def reg_env():
    tenant = TenantFactory(institution_type="school", name="Greenfield Academy")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYear.objects.create(
        branch=branch,
        name="2024-25",
        is_current=True,
        start_date=datetime.date(2024, 6, 1),
        end_date=datetime.date(2025, 4, 30),
    )
    period = AcademicPeriod.objects.create(
        academic_year=year,
        period_type="term",
        sequence=1,
        name="Term 1",
        start_date=datetime.date(2024, 6, 1),
        end_date=datetime.date(2024, 10, 31),
    )
    dept = Department.objects.create(branch=branch, name="Science", department_type="stream")
    course = Course.objects.create(department=dept, name="Grade 9")
    batch = Batch.objects.create(course=course, academic_year=year, name="A")
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919800000010",
        custom_login_id=None,
        must_change_password=False,
    )
    s1_user = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="GFA-9A-001",
        must_change_password=False,
    )
    s2_user = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="GFA-9A-002",
        must_change_password=False,
    )
    s1 = StudentProfile.objects.create(user=s1_user, current_batch=batch, academic_status=AcademicStatus.ACTIVE)
    s2 = StudentProfile.objects.create(user=s2_user, current_batch=batch, academic_status=AcademicStatus.ACTIVE)
    from apps.admissions.queries.enrollment import resolve_enrollment_for_profile
    resolve_enrollment_for_profile(s1)
    resolve_enrollment_for_profile(s2)
    return dict(
        tenant=tenant,
        branch=branch,
        period=period,
        batch=batch,
        admin=admin,
        s1=s1,
        s2=s2,
    )


def _create_paid_exam(env, client, fee_paise=50000):
    resp = client.post(
        reverse("examinations:exam-list"),
        {
            "name": "Final Exam",
            "examType": "final",
            "academicPeriodId": str(env["period"].id),
            "examFeePaise": fee_paise,
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return _data(resp)["exam"]["id"]


def test_bulk_register_creates_invoices(reg_env):
    client = _client(reg_env["admin"])
    exam_id = _create_paid_exam(reg_env, client, fee_paise=50000)

    resp = client.post(
        reverse("examinations:exam-register", kwargs={"exam_id": exam_id}),
        {"classSectionId": str(reg_env["batch"].id)},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    body = _data(resp)
    assert len(body["registrations"]) == 2
    assert body["registrations"][0]["feePaid"] is False
    assert body["registrations"][0]["feeInvoiceId"] is not None

    # Idempotent skip on re-register
    again = client.post(
        reverse("examinations:exam-register", kwargs={"exam_id": exam_id}),
        {"classSectionId": str(reg_env["batch"].id)},
        format="json",
    )
    assert again.status_code == 201
    assert len(_data(again)["registrations"]) == 0
    assert len(_data(again)["skippedStudentIds"]) == 2


def test_hall_ticket_blocked_until_fee_paid(reg_env):
    """EC-EXAM-01 — unpaid exam fee returns 403 exam_fee_unpaid."""
    client = _client(reg_env["admin"])
    exam_id = _create_paid_exam(reg_env, client, fee_paise=50000)
    reg_resp = client.post(
        reverse("examinations:exam-register", kwargs={"exam_id": exam_id}),
        {"classSectionId": str(reg_env["batch"].id)},
        format="json",
    )
    registration_id = _data(reg_resp)["registrations"][0]["id"]

    blocked = client.get(reverse("examinations:hall-ticket", kwargs={"registration_id": registration_id}))
    assert blocked.status_code == 403
    assert blocked.json().get("message", "").lower().find("exam fee") >= 0


def test_hall_ticket_after_payment(reg_env):
    client = _client(reg_env["admin"])
    exam_id = _create_paid_exam(reg_env, client, fee_paise=50000)
    reg_resp = client.post(
        reverse("examinations:exam-register", kwargs={"exam_id": exam_id}),
        {"classSectionId": str(reg_env["batch"].id)},
        format="json",
    )
    registration = next(
        r for r in _data(reg_resp)["registrations"] if r["studentId"] == str(reg_env["s1"].id)
    )
    invoice = get_invoice_by_id(registration["feeInvoiceId"])
    apply_amount_to_invoice(invoice, invoice.total_paise)

    ticket_resp = client.get(
        reverse("examinations:hall-ticket", kwargs={"registration_id": registration["id"]})
    )
    assert ticket_resp.status_code == 200, ticket_resp.content
    ticket = _data(ticket_resp)["hallTicket"]
    assert ticket["canDownload"] is True
    assert ticket["rollNumber"] == "GFA-9A-001"
    assert ticket["content"]


def test_zero_fee_allows_immediate_hall_ticket(reg_env):
    client = _client(reg_env["admin"])
    exam_id = _create_paid_exam(reg_env, client, fee_paise=0)
    reg_resp = client.post(
        reverse("examinations:exam-register", kwargs={"exam_id": exam_id}),
        {"classSectionId": str(reg_env["batch"].id)},
        format="json",
    )
    registration = _data(reg_resp)["registrations"][0]
    assert registration["feePaid"] is True

    ticket_resp = client.get(
        reverse("examinations:hall-ticket", kwargs={"registration_id": registration["id"]})
    )
    assert ticket_resp.status_code == 200
