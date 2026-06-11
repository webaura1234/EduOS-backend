"""Queries — Refund."""

from apps.fees.models import Refund


def create_refund(
    *,
    payment,
    amount_paise,
    reason="",
    status="requested",
    approved_by=None,
    razorpay_refund_id=None,
    idempotency_key=None,
    user=None,
) -> Refund:
    return Refund.objects.create(
        payment=payment,
        amount_paise=amount_paise,
        reason=reason,
        status=status,
        approved_by=approved_by,
        razorpay_refund_id=razorpay_refund_id,
        idempotency_key=idempotency_key,
        created_by=user,
        updated_by=user,
    )


def update_refund(refund: Refund, fields: dict, user=None) -> Refund:
    for k, v in fields.items():
        setattr(refund, k, v)
    if user:
        refund.updated_by = user
    update_fields = list(fields.keys()) + ["updated_at"]
    if user:
        update_fields.append("updated_by")
    refund.save(update_fields=update_fields)
    return refund


def list_refunds(branch_id, status=None):
    qs = Refund.objects.filter(payment__invoice__branch_id=branch_id, is_active=True).select_related(
        "payment", "payment__invoice", "payment__invoice__student", "payment__invoice__student__user"
    )
    if status:
        qs = qs.filter(status=status)
    return qs.order_by("-created_at")


def get_refund(branch_id, refund_id) -> Refund | None:
    try:
        return Refund.objects.select_related("payment", "payment__invoice").get(
            payment__invoice__branch_id=branch_id, pk=refund_id, is_active=True
        )
    except (Refund.DoesNotExist, ValueError, TypeError):
        return None


def get_refund_for_update(refund_id) -> Refund | None:
    return Refund.objects.select_for_update().filter(pk=refund_id, is_active=True).first()


def get_payment_for_update(payment_id):
    from apps.fees.models import Payment
    return Payment.objects.select_for_update().filter(pk=payment_id, is_active=True).first()


def sum_refunds_for_payment(payment_id, statuses) -> int:
    from django.db.models import Sum
    return Refund.objects.filter(
        payment_id=payment_id, status__in=statuses, is_active=True
    ).aggregate(t=Sum("amount_paise")).get("t") or 0
