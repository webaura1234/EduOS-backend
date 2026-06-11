"""Tests for fees interactors."""

import datetime
import pytest
from django.core.exceptions import ValidationError

from apps.fees.enums import ConcessionStatus, CreditNoteStatus, InvoiceStatus, PaymentMethod, PaymentStatus, RefundStatus
from apps.fees.models import ConcessionRequest, CreditNote, FeeInvoice, FeeStructure, Payment, Receipt, Refund
from apps.fees.interactors import (
    ApproveConcessionRequestInteractor,
    ApproveCreditNoteInteractor,
    ApproveRefundInteractor,
    CreateConcessionRequestInteractor,
    CreateConcessionRuleInteractor,
    CreateCreditNoteInteractor,
    CreatePaymentOrderInteractor,
    GetCollectionDashboardInteractor,
    RecordOfflinePaymentInteractor,
    ReconcilePendingPaymentInteractor,
    RequestRefundInteractor,
    VerifyPaymentCaptureInteractor,
    generate_invoices_for_batch,
)

pytestmark = pytest.mark.django_db


def test_invoice_generation_lifecycle(branch, batch, academic_year, student_profile):
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        name="Grade 10 General",
        components=[
            {"kind": "tuition", "label": "Tuition", "amount_paise": 5000000, "installment_no": 1, "due_date": "2024-07-10"},
            {"kind": "transport", "label": "Transport", "amount_paise": 1000000, "installment_no": 2, "due_date": "2024-09-10"},
        ],
    )

    invoices = generate_invoices_for_batch(
        branch=branch,
        batch_id=batch.id,
        academic_year=academic_year,
        fee_structure=fs,
    )
    
    assert len(invoices) == 1
    invoice = invoices[0]
    assert invoice.total_paise == 6000000
    assert invoice.status == InvoiceStatus.DUE
    assert invoice.lines.count() == 2
    assert invoice.installments.count() == 2

    inst1 = invoice.installments.get(sequence=1)
    inst2 = invoice.installments.get(sequence=2)
    assert inst1.amount_paise == 5000000
    assert inst2.amount_paise == 1000000


def test_payment_and_capture_verification(branch, student_profile, academic_year, batch):
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 5000, "installment_no": 1, "due_date": "2024-07-10"}],
    )
    invoice = generate_invoices_for_batch(branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs)[0]

    # Create Order
    creator = CreatePaymentOrderInteractor(
        invoice_id=invoice.id,
        amount_paise=5000,
        method=PaymentMethod.RAZORPAY,
        payer_user=student_profile.user,
        idempotency_key="key-1234",
    )
    payment = creator.execute()
    assert payment.status == PaymentStatus.PENDING
    assert payment.razorpay_order_id.startswith("order_sandbox_")

    # Verify Capture (mocked gateway always treats fetch as captured)
    verifier = VerifyPaymentCaptureInteractor(
        payment_id=payment.id,
        razorpay_payment_id="pay_sandbox_1",
    )
    captured_payment = verifier.execute()
    assert captured_payment.status == PaymentStatus.CAPTURED
    assert Receipt.objects.filter(payment=captured_payment).exists()

    invoice.refresh_from_db()
    assert invoice.paid_paise == 5000
    assert invoice.status == InvoiceStatus.PAID


def test_duplicate_payment_refunds_excess(branch, student_profile, academic_year, batch):
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 5000, "installment_no": 1, "due_date": "2024-07-10"}],
    )
    invoice = generate_invoices_for_batch(branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs)[0]

    # Create the duplicate online payment order first (when invoice is still DUE)
    payment = CreatePaymentOrderInteractor(
        invoice_id=invoice.id,
        amount_paise=5000,
        method=PaymentMethod.RAZORPAY,
        payer_user=student_profile.user,
        idempotency_key="key-dup",
    ).execute()

    # Now capture the first payment offline
    RecordOfflinePaymentInteractor(
        invoice_id=invoice.id,
        amount_paise=5000,
        method=PaymentMethod.CASH,
        payer_user=student_profile.user,
    ).execute()
    
    invoice.refresh_from_db()
    assert invoice.status == InvoiceStatus.PAID

    # Now verify the duplicate capture of the online payment, which should trigger auto-refund
    VerifyPaymentCaptureInteractor(
        payment_id=payment.id,
        razorpay_payment_id="pay_sandbox_dup",
    ).execute()

    # Verify auto-refund requested (EC-FEE-04)
    assert Refund.objects.filter(payment=payment, status=RefundStatus.REQUESTED, amount_paise=5000).exists()


def test_concessions_and_credit_notes(branch, student_profile, academic_year, batch, admin):
    # Concession rule
    rule_creator = CreateConcessionRuleInteractor(
        branch=branch,
        name="10% Scholarship",
        percent=10,
    )
    rule = rule_creator.execute()

    # Request concession
    req_creator = CreateConcessionRequestInteractor(
        branch=branch,
        student=student_profile,
        rule_id=rule.id,
        amount_paise=500, # 10% of 5000
        requested_by=admin,
    )
    req = req_creator.execute()
    assert req.status == ConcessionStatus.PENDING

    # Approve concession request
    ApproveConcessionRequestInteractor(
        request_id=req.id,
        status=ConcessionStatus.APPROVED,
        approver_user=admin,
    ).execute()

    # Verify assignment picks it up
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 5000, "installment_no": 1, "due_date": "2024-07-10"}],
    )
    invoice = generate_invoices_for_batch(branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs)[0]
    
    # 5000 - 500 = 4500
    assert invoice.total_paise == 4500

    # Credit Note (retroactive scholarship)
    cn = CreateCreditNoteInteractor(
        branch=branch,
        student=student_profile,
        invoice_id=invoice.id,
        amount_paise=1000,
        reason="Good grades credit",
        user=admin,
    ).execute()
    assert cn.status == CreditNoteStatus.PENDING

    # Approve credit note
    ApproveCreditNoteInteractor(
        credit_note_id=cn.id,
        status=CreditNoteStatus.APPROVED,
        approver_user=admin,
    ).execute()

    invoice.refresh_from_db()
    assert invoice.paid_paise == 1000
    assert invoice.balance_paise == 3500


def test_reconciliation_and_refunds(branch, student_profile, academic_year, batch, admin):
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 5000, "installment_no": 1, "due_date": "2024-07-10"}],
    )
    invoice = generate_invoices_for_batch(branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs)[0]

    # Offline payment
    payment = RecordOfflinePaymentInteractor(
        invoice_id=invoice.id,
        amount_paise=5000,
        method=PaymentMethod.CASH,
        payer_user=student_profile.user,
        user=admin,
    ).execute()

    invoice.refresh_from_db()
    assert invoice.status == InvoiceStatus.PAID

    # Request Refund
    refund = RequestRefundInteractor(
        payment_id=payment.id,
        amount_paise=2000,
        reason="Typo in cash collection",
        user=admin,
    ).execute()
    assert refund.status == RefundStatus.REQUESTED

    # Approve Refund
    ApproveRefundInteractor(
        refund_id=refund.id,
        approver_user=admin,
    ).execute()

    invoice.refresh_from_db()
    assert invoice.paid_paise == 3000
    assert invoice.status == InvoiceStatus.PARTIAL


def test_collection_metrics_dashboard(branch, student_profile, academic_year, batch, admin):
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 5000, "installment_no": 1, "due_date": "2024-07-10"}],
    )
    generate_invoices_for_batch(branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs)

    dashboard = GetCollectionDashboardInteractor(branch_id=branch.id).execute()
    assert dashboard["totalInvoicedPaise"] == 5000
    assert dashboard["totalCollectedPaise"] == 0
    assert dashboard["totalPendingPaise"] == 5000
