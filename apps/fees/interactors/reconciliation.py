"""Reconciliation interactors."""

from django.utils import timezone
from datetime import timedelta
from apps.fees.enums import PaymentStatus
from apps.fees.interactors.payment import VerifyPaymentCaptureInteractor
from apps.fees.queries.payment import list_pending_payments_for_branch, update_payment


class ReconcilePendingPaymentInteractor:
    """Reconciles pending payments that are older than 5 minutes by querying Razorpay."""

    def __init__(self, branch_id):
        self.branch_id = branch_id

    def execute(self) -> int:
        cutoff = timezone.now() - timedelta(minutes=5)
        # Find payments that are pending/created before cutoff
        pending_payments = list_pending_payments_for_branch(self.branch_id, cutoff)

        reconciled_count = 0
        for payment in pending_payments:
            if not payment.razorpay_payment_id:
                # If we don't have a payment ID after 5 mins, mark as failed
                update_payment(payment, {"status": PaymentStatus.FAILED})
                reconciled_count += 1
                continue

            try:
                # Try to capture/verify
                verifier = VerifyPaymentCaptureInteractor(
                    payment_id=payment.id,
                    razorpay_payment_id=payment.razorpay_payment_id,
                )
                verifier.execute()
                reconciled_count += 1
            except Exception:
                # Swallow and log or set to requires_review if fetch fails
                update_payment(payment, {"status": PaymentStatus.REQUIRES_REVIEW})
                reconciled_count += 1

        return reconciled_count
