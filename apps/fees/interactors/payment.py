"""Payment interactors."""

import datetime
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.fees.enums import InvoiceStatus, PaymentMethod, PaymentStatus, RefundStatus
from apps.fees.helpers.paise import financial_year_for
from apps.fees.models import Payment
from apps.fees.queries.invoice import (
    apply_amount_to_invoice,
    get_invoice_by_id,
    get_invoice_for_update,
)
from apps.fees.queries.payment import (
    create_payment,
    get_payment_by_idempotency_key,
    get_payment_by_order_for_update,
    get_payment_for_update,
    update_payment,
)
from apps.fees.queries.receipt import create_receipt, get_receipt_counter, next_receipt_number
from apps.fees.queries.refund import create_refund
from apps.integrations.adapters.payments import get_gateway


def _issue_receipt(invoice, payment, user=None):
    """Allocate a gap-free receipt number (locked counter) and create the receipt."""
    fy = financial_year_for(timezone.localdate())
    counter = get_receipt_counter(invoice.branch_id, fy)
    number = next_receipt_number(counter)
    create_receipt(branch=invoice.branch, payment=payment, sequence_number=number,
                   financial_year=fy, issued_at=timezone.now(), user=user)


def _auto_refund(payment, amount_paise, reason):
    create_refund(payment=payment, amount_paise=amount_paise, reason=reason,
                  status=RefundStatus.REQUESTED, idempotency_key=f"refund_auto_{payment.id.hex}")


class CreatePaymentOrderInteractor:
    """Creates a new payment attempt, initiating an order with Razorpay if online."""

    def __init__(self, invoice_id, amount_paise, method, payer_user, idempotency_key):
        self.invoice_id = invoice_id
        self.amount_paise = amount_paise
        self.method = method
        self.payer_user = payer_user
        self.idempotency_key = idempotency_key

    @transaction.atomic
    def execute(self) -> Payment:
        # Validate idempotency key
        existing = get_payment_by_idempotency_key(self.idempotency_key)
        if existing:
            return existing

        invoice = get_invoice_by_id(self.invoice_id)
        if invoice is None:
            raise ValidationError("Invoice not found.")

        if invoice.status == InvoiceStatus.PAID and self.amount_paise > 0:
            raise ValidationError("This invoice has already been fully paid.")

        if self.amount_paise <= 0:
            raise ValidationError("Payment amount must be greater than zero.")

        # Create payment record
        payment = create_payment(
            invoice=invoice,
            amount_paise=self.amount_paise,
            method=self.method,
            status=PaymentStatus.CREATED,
            payer=self.payer_user,
            idempotency_key=self.idempotency_key,
            user=self.payer_user,
        )

        if self.method == PaymentMethod.RAZORPAY:
            gateway = get_gateway()
            try:
                order = gateway.create_order(
                    amount_paise=self.amount_paise,
                    receipt=f"rcpt_{payment.id.hex[:12]}",
                    notes={"invoice_id": str(invoice.id), "payment_id": str(payment.id)},
                )
                update_payment(payment, {"razorpay_order_id": order["order_id"],
                                         "status": PaymentStatus.PENDING})
            except Exception as exc:
                update_payment(payment, {"status": PaymentStatus.FAILED})
                raise ValidationError(f"Failed to initiate order with payment gateway: {exc}")

        return payment


class VerifyPaymentCaptureInteractor:
    """Verifies and processes a captured payment from Razorpay (called by webhook or client verify)."""

    def __init__(self, payment_id=None, razorpay_payment_id=None, razorpay_order_id=None, signature=None):
        self.payment_id = payment_id
        self.razorpay_payment_id = razorpay_payment_id
        self.razorpay_order_id = razorpay_order_id
        self.signature = signature

    @transaction.atomic
    def execute(self) -> Payment:
        # Find payment by ID or Razorpay Order ID (row-locked).
        payment = None
        if self.payment_id:
            payment = get_payment_for_update(self.payment_id)
        elif self.razorpay_order_id:
            payment = get_payment_by_order_for_update(self.razorpay_order_id)

        if not payment:
            raise ValidationError("Payment record not found.")

        # Deduplicate: if already captured, return immediately (EC-FEE-02).
        if payment.status == PaymentStatus.CAPTURED:
            return payment

        # Verify against gateway.
        gateway = get_gateway()
        gw_payment = gateway.fetch_payment(self.razorpay_payment_id)
        if gw_payment.get("status") not in ("captured", "authorized"):
            update_payment(payment, {"status": PaymentStatus.FAILED,
                                     "razorpay_payment_id": self.razorpay_payment_id})
            return payment

        update_payment(payment, {"status": PaymentStatus.CAPTURED,
                                 "razorpay_payment_id": self.razorpay_payment_id,
                                 "captured_at": timezone.now()})

        invoice = payment.invoice
        amount_to_apply = payment.amount_paise
        initial_balance = invoice.balance_paise

        # Overpayment → auto-refund the excess (EC-FEE-04).
        if initial_balance == 0:
            _auto_refund(payment, amount_to_apply, "Auto-refund: Invoice was already fully paid.")
            amount_to_apply = 0
        elif amount_to_apply > initial_balance:
            _auto_refund(payment, amount_to_apply - initial_balance,
                         "Auto-refund: Payment exceeds invoice outstanding balance.")
            amount_to_apply = initial_balance

        if amount_to_apply > 0:
            apply_amount_to_invoice(invoice, amount_to_apply)

        _issue_receipt(invoice, payment)
        return payment


class RecordOfflinePaymentInteractor:
    """Allows Admin to record an offline payment (cash, cheque, bank transfer)."""

    def __init__(self, invoice_id, amount_paise, method, payer_user, reference_no=None, user=None):
        self.invoice_id = invoice_id
        self.amount_paise = amount_paise
        self.method = method
        self.payer_user = payer_user
        self.reference_no = reference_no
        self.user = user

    @transaction.atomic
    def execute(self) -> Payment:
        if self.method == PaymentMethod.RAZORPAY:
            raise ValidationError("Cannot record online Razorpay payment via offline endpoint.")

        invoice = get_invoice_for_update(self.invoice_id)
        if invoice is None:
            raise ValidationError("Invoice not found.")

        if invoice.status == InvoiceStatus.PAID:
            raise ValidationError("Invoice is already fully paid.")

        if self.amount_paise <= 0:
            raise ValidationError("Payment amount must be greater than zero.")

        # Create captured offline payment.
        ref = self.reference_no or f"offline_{timezone.now().timestamp()}"
        payment = create_payment(
            invoice=invoice, amount_paise=self.amount_paise, method=self.method,
            status=PaymentStatus.CAPTURED, payer=self.payer_user,
            idempotency_key=f"offline_key_{invoice.id.hex}_{ref}", user=self.user,
        )
        update_payment(payment, {"captured_at": timezone.now()}, user=self.user)

        amount_to_apply = self.amount_paise
        initial_balance = invoice.balance_paise

        if amount_to_apply > initial_balance:
            _auto_refund(payment, amount_to_apply - initial_balance,
                         "Auto-refund: Offline payment exceeds invoice outstanding balance.")
            amount_to_apply = initial_balance

        if amount_to_apply > 0:
            apply_amount_to_invoice(invoice, amount_to_apply, user=self.user)

        _issue_receipt(invoice, payment, user=self.user)
        return payment
