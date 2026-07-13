"""Promotion fee carry-forward — lifecycle close without double-counting."""

import datetime

import pytest
from django.core.exceptions import ValidationError

from apps.academics.models import AcademicYear, Batch, Course, Department
from apps.academics.models.promotion import AcademicPromotionSession, PromotionSessionStatus
from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.admissions.tests.factories import StudentEnrollmentFactory
from apps.fees.enums import CarryForwardState, FeeComponentKind, InvoiceStatus, OpeningBalanceSource, PaymentMethod
from apps.fees.interactors.payment import CreatePaymentOrderInteractor, RecordOfflinePaymentInteractor
from apps.fees.interactors.promotion_carry_forward import setup_promotion_fees
from apps.fees.models import FeeInvoice, FeeInvoiceLine, FeeStructure
from apps.fees.queries.invoice import outstanding_balance_paise
from apps.fees.views.admin_overview import _fee_charges_by_student, _ledger_and_collection
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def carry_env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        custom_login_id=None,
        must_change_password=False,
    )
    source_year = AcademicYear.objects.create(
        branch=branch,
        name="2024-25",
        is_current=False,
        start_date=datetime.date(2024, 4, 1),
        end_date=datetime.date(2025, 3, 31),
    )
    target_year = AcademicYear.objects.create(
        branch=branch,
        name="2025-26",
        is_current=True,
        start_date=datetime.date(2025, 4, 1),
        end_date=datetime.date(2026, 3, 31),
    )
    dept = Department.objects.create(branch=branch, name="Primary", department_type="academic")
    course = Course.objects.create(department=dept, name="Class 5")
    batch = Batch.objects.create(course=course, academic_year=target_year, name="A")
    source_batch = Batch.objects.create(course=course, academic_year=source_year, name="A")

    student = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="CF-STU-1",
        first_name="Carry",
        must_change_password=False,
    )
    profile = StudentProfile.objects.create(user=student, current_batch=batch)
    source_enrollment = StudentEnrollmentFactory(
        student_profile=profile,
        branch=branch,
        batch=source_batch,
        academic_year=source_year,
    )
    new_enrollment = StudentEnrollmentFactory(
        student_profile=profile,
        branch=branch,
        batch=batch,
        academic_year=target_year,
    )
    structure = FeeStructure.objects.create(
        branch=branch,
        name="Class 5 Fees",
        academic_year=target_year,
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 1000000, "installment_no": 1}],
        status="published",
    )
    session = AcademicPromotionSession.objects.create(
        branch=branch,
        source_year=source_year,
        target_year=target_year,
        status=PromotionSessionStatus.APPROVED,
    )
    return {
        "tenant": tenant,
        "branch": branch,
        "admin": admin,
        "source_year": source_year,
        "target_year": target_year,
        "source_enrollment": source_enrollment,
        "new_enrollment": new_enrollment,
        "structure": structure,
        "session": session,
        "profile": profile,
        "student": student,
    }


def _source_invoices(env, *, due_paise=500000, partial_paise=300000, partial_paid=100000):
    due_inv = FeeInvoice.objects.create(
        branch=env["branch"],
        student=env["source_enrollment"],
        total_paise=due_paise,
        paid_paise=0,
        status=InvoiceStatus.DUE,
    )
    FeeInvoiceLine.objects.create(
        invoice=due_inv,
        kind=FeeComponentKind.TUITION,
        label="Tuition",
        amount_paise=due_paise,
    )
    partial_inv = FeeInvoice.objects.create(
        branch=env["branch"],
        student=env["source_enrollment"],
        total_paise=partial_paise,
        paid_paise=partial_paid,
        status=InvoiceStatus.PARTIAL,
    )
    FeeInvoiceLine.objects.create(
        invoice=partial_inv,
        kind=FeeComponentKind.TUITION,
        label="Tuition",
        amount_paise=partial_paise,
    )
    return due_inv, partial_inv


def _run_carry_forward(env):
    return setup_promotion_fees(
        branch_id=env["branch"].pk,
        branch=env["branch"],
        new_enrollment=env["new_enrollment"],
        fee_structure_id=env["structure"].pk,
        source_enrollment_id=env["source_enrollment"].pk,
        source_year=env["source_year"],
        source_year_label=env["source_year"].name,
        promotion_session=env["session"],
        user=env["admin"],
    )


def test_no_double_count_outstanding(carry_env):
    due_inv, partial_inv = _source_invoices(carry_env)
    _run_carry_forward(carry_env)

    due_inv.refresh_from_db()
    partial_inv.refresh_from_db()
    assert due_inv.status == InvoiceStatus.DUE
    assert partial_inv.status == InvoiceStatus.PARTIAL
    assert due_inv.carry_forward_state == CarryForwardState.CARRIED_FORWARD
    assert partial_inv.carry_forward_state == CarryForwardState.CARRIED_FORWARD
    assert due_inv.carried_forward_to_id is not None
    assert partial_inv.carried_forward_to_id == due_inv.carried_forward_to_id

    assert outstanding_balance_paise(carry_env["source_enrollment"].pk) == 0
    assert outstanding_balance_paise(carry_env["new_enrollment"].pk) == 700000
    total = (
        outstanding_balance_paise(carry_env["source_enrollment"].pk)
        + outstanding_balance_paise(carry_env["new_enrollment"].pk)
    )
    assert total == 700000


def test_partial_source_invoice_keeps_status(carry_env):
    _, partial_inv = _source_invoices(carry_env)
    FeeInvoice.objects.filter(student=carry_env["source_enrollment"]).exclude(pk=partial_inv.pk).delete()

    _run_carry_forward(carry_env)
    partial_inv.refresh_from_db()
    assert partial_inv.status == InvoiceStatus.PARTIAL
    assert partial_inv.paid_paise == 100000
    assert partial_inv.total_paise == 300000
    assert outstanding_balance_paise(carry_env["new_enrollment"].pk) == 200000


def test_opening_invoice_audit_metadata(carry_env):
    due_inv, partial_inv = _source_invoices(carry_env)
    _run_carry_forward(carry_env)

    opening = FeeInvoice.objects.get(
        student=carry_env["new_enrollment"],
        opening_balance_source=OpeningBalanceSource.PROMOTION,
    )
    assert opening.opening_balance_source_year_id == carry_env["source_year"].pk
    assert opening.promotion_session_id == carry_env["session"].pk
    source_ids = set(opening.carried_from_invoices.values_list("pk", flat=True))
    assert source_ids == {due_inv.pk, partial_inv.pk}


def test_payment_blocked_on_carried_forward_invoice(carry_env):
    due_inv, _ = _source_invoices(carry_env)
    _run_carry_forward(carry_env)
    due_inv.refresh_from_db()

    with pytest.raises(ValidationError, match="carried forward"):
        CreatePaymentOrderInteractor(
            invoice_id=due_inv.pk,
            amount_paise=10000,
            method=PaymentMethod.CASH,
            payer_user=carry_env["student"],
            idempotency_key="cf-block-online",
        ).execute()

    with pytest.raises(ValidationError, match="carried forward"):
        RecordOfflinePaymentInteractor(
            invoice_id=due_inv.pk,
            amount_paise=10000,
            method=PaymentMethod.CASH,
            payer_user=carry_env["student"],
            user=carry_env["admin"],
        ).execute()


def test_admin_ledger_excludes_carried_forward_outstanding(carry_env):
    _source_invoices(carry_env)
    _run_carry_forward(carry_env)

    _, collection = _ledger_and_collection(
        carry_env["branch"],
        academic_year_id=str(carry_env["source_year"].pk),
    )
    assert collection["outstandingTotal"] == 0.0

    charges = _fee_charges_by_student(
        carry_env["branch"],
        academic_year_id=str(carry_env["source_year"].pk),
    )
    sid = str(carry_env["profile"].pk)
    rows = charges[sid]
    assert len(rows) == 2
    assert all(r["carryForward"] is True for r in rows)
    assert all(r["balance"] == 0.0 for r in rows)
    assert {r["originalStatus"] for r in rows} == {"due", "partial"}
    assert all(r["carriedForwardToYearLabel"] == carry_env["target_year"].name for r in rows)

    _, current_collection = _ledger_and_collection(
        carry_env["branch"],
        academic_year_id=str(carry_env["target_year"].pk),
    )
    assert current_collection["outstandingTotal"] == 7000.0
