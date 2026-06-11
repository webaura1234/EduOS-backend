"""Refund interactors."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.fees.enums import PaymentMethod, PaymentStatus, RefundStatus
from apps.fees.models import Refund
from apps.fees.queries.invoice import reverse_amount_from_invoice
from apps.fees.queries.payment import update_payment
from apps.fees.queries.refund import (
    create_refund,
    get_payment_for_update,
    get_refund_for_update,
    sum_refunds_for_payment,
    update_refund,
)
from apps.integrations.adapters.payments import get_gateway


class RequestRefundInteractor:
    """Creates a refund request for a captured payment."""

    def __init__(self, payment_id, amount_paise, reason, user):
        self.payment_id = payment_id
        self.amount_paise = amount_paise
        self.reason = reason
        self.user = user

    @transaction.atomic
    def execute(self) -> Refund:
        payment = get_payment_for_update(self.payment_id)
        if not payment:
            raise ValidationError("Payment not found.")
        if payment.status != PaymentStatus.CAPTURED:
            raise ValidationError("Can only refund captured payments.")
        if self.amount_paise <= 0:
            raise ValidationError("Refund amount must be greater than zero.")

        already = sum_refunds_for_payment(
            payment.id, [RefundStatus.REQUESTED, RefundStatus.APPROVED, RefundStatus.PROCESSED]
        )
        if already + self.amount_paise > payment.amount_paise:
            raise ValidationError("Total refund amount exceeds original payment amount.")

        return create_refund(
            payment=payment, amount_paise=self.amount_paise, reason=self.reason,
            status=RefundStatus.REQUESTED,
            idempotency_key=f"refund_req_{payment.id.hex}_{timezone.now().timestamp()}",
            user=self.user,
        )


class ApproveRefundInteractor:
    """Approves a refund, calls the gateway if online, and reverses ledger balances."""

    def __init__(self, refund_id, approver_user):
        self.refund_id = refund_id
        self.approver_user = approver_user

    @transaction.atomic
    def execute(self) -> Refund:
        refund = get_refund_for_update(self.refund_id)
        if not refund:
            raise ValidationError("Refund request not found.")
        if refund.status != RefundStatus.REQUESTED:
            raise ValidationError("Refund request is not in pending/requested status.")

        payment = refund.payment
        invoice = payment.invoice

        update_refund(refund, {"status": RefundStatus.APPROVED, "approved_by": self.approver_user})

        if payment.method == PaymentMethod.RAZORPAY and payment.razorpay_payment_id:
            gateway = get_gateway()
            try:
                gw_refund = gateway.create_refund(
                    payment_id=payment.razorpay_payment_id, amount_paise=refund.amount_paise
                )
                update_refund(refund, {"razorpay_refund_id": gw_refund["refund_id"],
                                       "status": RefundStatus.PROCESSED})
            except Exception as exc:
                update_refund(refund, {"status": RefundStatus.FAILED})
                raise ValidationError(f"Failed to issue refund on payment gateway: {exc}")
        else:
            update_refund(refund, {"status": RefundStatus.PROCESSED})

        # Reverse the amount from the invoice + installments.
        reverse_amount_from_invoice(invoice, refund.amount_paise)

        # If the whole payment is now refunded, flip the payment status.
        if sum_refunds_for_payment(payment.id, [RefundStatus.PROCESSED]) >= payment.amount_paise:
            update_payment(payment, {"status": PaymentStatus.REFUNDED})

        return refund
