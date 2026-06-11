"""Queries — Payment."""

from apps.fees.enums import PaymentStatus
from apps.fees.models import Payment


def get_payment_by_idempotency_key(key) -> Payment | None:
    return Payment.objects.filter(idempotency_key=key).first()


def get_payment_for_update(payment_id) -> Payment | None:
    """Row-locked fetch for the capture transaction."""
    return Payment.objects.select_for_update().filter(pk=payment_id, is_active=True).first()


def get_payment_by_order_for_update(order_id) -> Payment | None:
    return Payment.objects.select_for_update().filter(razorpay_order_id=order_id, is_active=True).first()


def list_pending_payments(*, older_than=None):
    """Razorpay payments still pending (for reconciliation, EC-FEE-03)."""
    qs = Payment.objects.filter(status=PaymentStatus.PENDING, method="razorpay", is_active=True)
    if older_than is not None:
        qs = qs.filter(created_at__lt=older_than)
    return qs.select_related("invoice")


def list_pending_payments_for_branch(branch_id, older_than):
    """Pending/created payments in a branch older than a cutoff (reconciliation)."""
    return Payment.objects.filter(
        invoice__branch_id=branch_id,
        status__in=[PaymentStatus.PENDING, PaymentStatus.CREATED],
        created_at__lt=older_than, is_active=True,
    )


def get_payment(branch_id, payment_id) -> Payment | None:
    try:
        return Payment.objects.select_related("invoice", "payer").get(
            invoice__branch_id=branch_id, pk=payment_id, is_active=True
        )
    except (Payment.DoesNotExist, ValueError, TypeError):
        return None


def get_payment_by_order_id(order_id) -> Payment | None:
    try:
        return Payment.objects.select_related("invoice", "payer").get(
            razorpay_order_id=order_id, is_active=True
        )
    except (Payment.DoesNotExist, ValueError, TypeError):
        return None


def get_payment_by_razorpay_payment_id(razorpay_payment_id) -> Payment | None:
    try:
        return Payment.objects.select_related("invoice", "payer").get(
            razorpay_payment_id=razorpay_payment_id, is_active=True
        )
    except (Payment.DoesNotExist, ValueError, TypeError):
        return None


def create_payment(
    *,
    invoice,
    amount_paise,
    method="razorpay",
    status="created",
    razorpay_order_id=None,
    razorpay_payment_id=None,
    payer=None,
    idempotency_key=None,
    user=None,
) -> Payment:
    return Payment.objects.create(
        invoice=invoice,
        amount_paise=amount_paise,
        method=method,
        status=status,
        razorpay_order_id=razorpay_order_id,
        razorpay_payment_id=razorpay_payment_id,
        payer=payer,
        idempotency_key=idempotency_key,
        created_by=user,
        updated_by=user,
    )


def update_payment(payment: Payment, fields: dict, user=None) -> Payment:
    for k, v in fields.items():
        setattr(payment, k, v)
    if user:
        payment.updated_by = user
    update_fields = list(fields.keys()) + ["updated_at"]
    if user:
        update_fields.append("updated_by")
    payment.save(update_fields=update_fields)
    return payment


def list_payments_for_invoice(invoice_id):
    return Payment.objects.filter(invoice_id=invoice_id, is_active=True).order_by("-created_at")
