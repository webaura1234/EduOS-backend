"""Tests for fees queries."""

import pytest

from apps.fees.queries import (
    create_assignment,
    create_installment,
    create_invoice,
    create_invoice_line,
    create_payment,
    create_receipt,
    create_refund,
    create_structure,
    get_assignment,
    get_invoice,
    get_payment,
    get_payment_by_order_id,
    get_payment_by_razorpay_payment_id,
    get_receipt_counter,
    get_structure,
    list_invoices,
    list_receipts,
    list_refunds,
    list_structures,
    update_payment,
    update_structure,
)

pytestmark = pytest.mark.django_db


def test_structure_queries(branch, academic_year):
    fs = create_structure(
        branch_id=branch.id,
        name="Class 10 Fees",
        academic_year_id=academic_year.id,
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 4000000, "installment_no": 1}],
    )
    
    assert fs.version == 1
    assert get_structure(branch.id, fs.id) == fs
    
    # List
    assert list(list_structures(branch.id)) == [fs]
    
    # Update
    updated = update_structure(fs, {"name": "Class 10 Revised"})
    assert updated.version == 2
    assert updated.name == "Class 10 Revised"


def test_invoice_queries(branch, student_profile):
    invoice = create_invoice(
        branch=branch,
        student=student_profile.enrollment,
        total_paise=10000,
    )
    assert get_invoice(branch.id, invoice.id) == invoice
    assert list(list_invoices(branch.id)) == [invoice]

    line = create_invoice_line(invoice=invoice, kind="tuition", label="Tuition", amount_paise=10000)
    assert line.invoice == invoice

    inst = create_installment(invoice=invoice, sequence=1, amount_paise=10000)
    assert inst.invoice == invoice


def test_payment_queries(branch, student_profile):
    invoice = create_invoice(
        branch=branch,
        student=student_profile.enrollment,
        total_paise=10000,
    )
    
    payment = create_payment(
        invoice=invoice,
        amount_paise=10000,
        razorpay_order_id="order_123",
        razorpay_payment_id="pay_123",
        idempotency_key="idemp_1",
    )
    
    assert get_payment(branch.id, payment.id) == payment
    assert get_payment_by_order_id("order_123") == payment
    assert get_payment_by_razorpay_payment_id("pay_123") == payment
    
    updated = update_payment(payment, {"status": "captured"})
    assert updated.status == "captured"


def test_receipt_queries(branch, student_profile):
    invoice = create_invoice(
        branch=branch,
        student=student_profile.enrollment,
        total_paise=10000,
    )
    payment = create_payment(
        invoice=invoice,
        amount_paise=10000,
        idempotency_key="idemp_receipt",
    )
    
    counter = get_receipt_counter(branch.id, "2024-25")
    assert counter.last_number == 0
    
    import django.utils.timezone
    receipt = create_receipt(
        branch=branch,
        payment=payment,
        sequence_number=1,
        financial_year="2024-25",
        issued_at=django.utils.timezone.now(),
    )
    
    assert list(list_receipts(branch.id)) == [receipt]


def test_refund_queries(branch, student_profile):
    invoice = create_invoice(
        branch=branch,
        student=student_profile.enrollment,
        total_paise=10000,
    )
    payment = create_payment(
        invoice=invoice,
        amount_paise=10000,
        idempotency_key="idemp_refund",
    )
    
    refund = create_refund(
        payment=payment,
        amount_paise=5000,
        idempotency_key="idemp_ref_act",
    )
    
    assert list(list_refunds(branch.id)) == [refund]
