"""Installments tab — ledger filters and fee charge breakdown."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.academics.models import AcademicYear, Batch
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory, CourseFactory
from apps.admissions.tests.factories import StudentEnrollmentFactory
from apps.fees.enums import FeeComponentKind
from apps.fees.models.invoice import FeeInvoice, FeeInvoiceLine, Installment
from apps.fees.views.admin_overview import (
    _fee_charges_by_student,
    _ledger_and_collection,
    _PRIOR_YEAR_BALANCE_PREFIX,
)
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
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919810000099",
        custom_login_id=None,
        must_change_password=False,
    )
    past_year = AcademicYearFactory(
        branch=branch,
        name="2024-25",
        is_current=False,
        start_date=datetime.date(2024, 4, 1),
        end_date=datetime.date(2025, 3, 31),
    )
    current_year = AcademicYearFactory(
        branch=branch,
        name="2025-26",
        is_current=True,
        start_date=datetime.date(2025, 4, 1),
        end_date=datetime.date(2026, 3, 31),
    )
    course = CourseFactory(department__branch=branch, name="Class 5")
    past_batch = BatchFactory(course=course, academic_year=past_year, name="A")
    current_batch = BatchFactory(course=course, academic_year=current_year, name="A")
    return dict(
        tenant=tenant,
        branch=branch,
        admin=admin,
        past_year=past_year,
        current_year=current_year,
        course=course,
        past_batch=past_batch,
        current_batch=current_batch,
    )


def _student_enrollment(env, *, batch, first_name):
    student = UserFactory(
        role=Role.STUDENT,
        tenant=env["tenant"],
        branch=env["branch"],
        custom_login_id=f"STU-{first_name}",
        first_name=first_name,
        last_name="",
        must_change_password=False,
    )
    profile = StudentProfile.objects.create(user=student)
    return StudentEnrollmentFactory(
        student_profile=profile,
        branch=env["branch"],
        batch=batch,
        academic_year=batch.academic_year,
    )


def test_installments_tab_defaults_to_current_year(env):
    past_enr = _student_enrollment(env, batch=env["past_batch"], first_name="Past")
    current_enr = _student_enrollment(env, batch=env["current_batch"], first_name="Current")
    FeeInvoice.objects.create(branch=env["branch"], student=past_enr, total_paise=100000, paid_paise=0)
    FeeInvoice.objects.create(branch=env["branch"], student=current_enr, total_paise=200000, paid_paise=0)

    body = _data(_client(env["admin"]).get(reverse("fees:admin-installments-tab")))
    names = {r["studentName"] for r in body["ledger"]}
    assert names == {"Current"}
    assert "feeChargesByStudent" in body
    assert body["batches"][0]["courseId"] is not None
    assert body["batches"][0]["sectionName"] is not None


def test_installments_tab_filters_by_academic_year(env):
    past_enr = _student_enrollment(env, batch=env["past_batch"], first_name="Past")
    current_enr = _student_enrollment(env, batch=env["current_batch"], first_name="Current")
    FeeInvoice.objects.create(branch=env["branch"], student=past_enr, total_paise=100000, paid_paise=0)
    FeeInvoice.objects.create(branch=env["branch"], student=current_enr, total_paise=200000, paid_paise=0)

    url = reverse("fees:admin-installments-tab")
    body = _data(
        _client(env["admin"]).get(url, {"academicYearId": str(env["past_year"].id)})
    )
    names = {r["studentName"] for r in body["ledger"]}
    assert names == {"Past"}
    row = body["ledger"][0]
    assert row["academicYearLabel"] == "2024-25"
    assert row["courseName"] == "Class 5"
    assert row["sectionName"] == "A"


def test_fee_charges_includes_exam_fee_without_installments(env):
    enr = _student_enrollment(env, batch=env["current_batch"], first_name="ExamKid")
    inv = FeeInvoice.objects.create(
        branch=env["branch"],
        student=enr,
        total_paise=50000,
        paid_paise=0,
        due_date=datetime.date(2025, 9, 1),
    )
    FeeInvoiceLine.objects.create(
        invoice=inv,
        kind=FeeComponentKind.EXAM,
        label="Exam fee — Mid-Term",
        amount_paise=50000,
    )

    charges = _fee_charges_by_student(
        env["branch"],
        academic_year_id=str(env["current_year"].id),
    )
    sid = str(enr.student_profile_id)
    assert len(charges[sid]) == 1
    row = charges[sid][0]
    assert row["label"] == "Exam fee — Mid-Term"
    assert row["category"] == "exam"
    assert row["amount"] == 500.0
    assert row["balance"] == 500.0


def test_fee_charges_marks_carry_forward(env):
    enr = _student_enrollment(env, batch=env["current_batch"], first_name="Carry")
    inv = FeeInvoice.objects.create(
        branch=env["branch"],
        student=enr,
        total_paise=75000,
        paid_paise=25000,
        due_date=datetime.date(2025, 8, 1),
    )
    FeeInvoiceLine.objects.create(
        invoice=inv,
        kind=FeeComponentKind.OTHER,
        label=f"{_PRIOR_YEAR_BALANCE_PREFIX} (2024-25)",
        amount_paise=75000,
    )

    charges = _fee_charges_by_student(
        env["branch"],
        academic_year_id=str(env["current_year"].id),
    )
    sid = str(enr.student_profile_id)
    row = charges[sid][0]
    assert row["isCarryForward"] is True
    assert row["category"] == "carry_forward"
    assert row["paid"] == 250.0
    assert row["balance"] == 500.0


def test_ledger_filters_by_course_and_batch(env):
    course4 = CourseFactory(department__branch=env["branch"], name="Class 4")
    batch4 = Batch.objects.create(course=course4, academic_year=env["current_year"], name="B")
    enr4 = _student_enrollment(env, batch=batch4, first_name="Four")
    enr5 = _student_enrollment(env, batch=env["current_batch"], first_name="Five")
    FeeInvoice.objects.create(branch=env["branch"], student=enr4, total_paise=90000, paid_paise=0)
    FeeInvoice.objects.create(branch=env["branch"], student=enr5, total_paise=60000, paid_paise=0)

    ledger, _ = _ledger_and_collection(
        env["branch"],
        academic_year_id=str(env["current_year"].id),
        course_id=str(course4.id),
        batch_id=str(batch4.id),
    )
    assert len(ledger) == 1
    assert ledger[0]["studentName"] == "Four"
    assert ledger[0]["courseName"] == "Class 4"


def test_installment_schedule_excludes_exam_only_invoice(env):
    enr = _student_enrollment(env, batch=env["current_batch"], first_name="Mixed")
    tuition_inv = FeeInvoice.objects.create(
        branch=env["branch"], student=enr, total_paise=300000, paid_paise=0,
    )
    Installment.objects.create(
        invoice=tuition_inv, sequence=1, amount_paise=300000, paid_paise=0,
        due_date=datetime.date(2025, 7, 10),
    )
    exam_inv = FeeInvoice.objects.create(branch=env["branch"], student=enr, total_paise=50000, paid_paise=0)
    FeeInvoiceLine.objects.create(
        invoice=exam_inv, kind=FeeComponentKind.EXAM, label="Exam fee", amount_paise=50000,
    )

    body = _data(
        _client(env["admin"]).get(
            reverse("fees:admin-installments-tab"),
            {"academicYearId": str(env["current_year"].id)},
        )
    )
    sid = str(enr.student_profile_id)
    assert len(body["installmentSchedulesByStudent"][sid]) == 1
    assert len(body["feeChargesByStudent"][sid]) == 1
    assert body["ledger"][0]["totalDue"] == 3500.0
