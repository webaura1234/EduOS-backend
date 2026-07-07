"""Queries — Payment."""

import datetime

from django.db.models import Count, Q, Sum
from django.db.models.functions import Coalesce

from apps.fees.enums import PaymentStatus
from apps.fees.models import Payment


def _utc_day_start(d: datetime.date) -> datetime.datetime:
    """UTC midnight for a calendar date — used for day-range filters below.

    Deliberately NOT Django's timezone-aware ``__date`` lookup: that converts
    using ``settings.TIME_ZONE`` (Asia/Kolkata here), which would silently shift
    a payment captured at e.g. 20:50 UTC into the *next* local calendar day.
    Payment timestamps have always been bucketed by their UTC calendar date
    (a ``.date()`` call on the UTC-aware datetime Django returns) — matching
    that exactly avoids changing which day a payment counts toward.
    """
    return datetime.datetime.combine(d, datetime.time.min, tzinfo=datetime.timezone.utc)


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


def list_payments_for_branch(branch_id, *, limit=300):
    """Recent payments across a branch (admin fees screen)."""
    return (
        Payment.objects.filter(invoice__branch_id=branch_id, is_active=True)
        .select_related(
            "invoice",
            "invoice__student__student_profile__user",
            "invoice__student__batch",
            "receipt",
        )
        .order_by("-created_at")[:limit]
    )


def list_payments_for_branch_filtered(
    branch_id, *, date_from=None, date_to=None, status=None, student_id=None, search=None,
):
    """Filterable/paginatable payments queryset for the admin Payments screen —
    unlike ``list_payments_for_branch``, this has no row cap; callers page it via
    ``apps.core.pagination.paginate_queryset``."""
    qs = Payment.objects.filter(invoice__branch_id=branch_id, is_active=True).annotate(
        effective_date=Coalesce("captured_at", "created_at"),
    )
    if date_from:
        qs = qs.filter(effective_date__gte=_utc_day_start(datetime.date.fromisoformat(date_from)))
    if date_to:
        qs = qs.filter(
            effective_date__lt=_utc_day_start(datetime.date.fromisoformat(date_to) + datetime.timedelta(days=1)),
        )
    if status:
        qs = qs.filter(status=status)
    if student_id:
        qs = qs.filter(invoice__student__student_profile_id=student_id)
    if search:
        qs = qs.filter(
            Q(invoice__student__student_profile__user__first_name__icontains=search)
            | Q(invoice__student__student_profile__user__last_name__icontains=search)
            | Q(razorpay_payment_id__icontains=search)
            | Q(receipt__sequence_number__icontains=search)
        )
    return qs.select_related(
        "invoice",
        "invoice__student__student_profile__user",
        "invoice__student__batch",
        "receipt",
    ).order_by("-effective_date")


def payment_summary_for_branch(
    branch_id, *, date_from=None, date_to=None, status=None, student_id=None,
) -> dict:
    """Aggregate count/total/method-breakdown for the same filters as
    ``list_payments_for_branch_filtered``, computed in one DB query instead of
    looping over the (potentially unbounded) matching rows in Python."""
    qs = Payment.objects.filter(invoice__branch_id=branch_id, is_active=True).annotate(
        effective_date=Coalesce("captured_at", "created_at"),
    )
    if date_from:
        qs = qs.filter(effective_date__gte=_utc_day_start(datetime.date.fromisoformat(date_from)))
    if date_to:
        qs = qs.filter(
            effective_date__lt=_utc_day_start(datetime.date.fromisoformat(date_to) + datetime.timedelta(days=1)),
        )
    if status:
        qs = qs.filter(status=status)
    if student_id:
        qs = qs.filter(invoice__student__student_profile_id=student_id)

    # Mirrors the frontend's method/source categorisation exactly (FeePayment.method
    # is already remapped from the raw DB value; "online" takes priority there
    # whenever the raw method is razorpay) — these four raw-method groups are
    # mutually exclusive, so order doesn't matter here.
    agg = qs.aggregate(
        count=Count("id"),
        total_paise=Sum("amount_paise"),
        cash=Count("id", filter=Q(method__in=["cash", "cheque"])),
        upi=Count("id", filter=Q(method__in=["bank_transfer", "upi"])),
        online=Count("id", filter=Q(method="razorpay")),
        other=Count("id", filter=~Q(method__in=["cash", "cheque", "bank_transfer", "upi", "razorpay"])),
    )
    return {
        "count": agg["count"] or 0,
        "totalPaise": agg["total_paise"] or 0,
        "methodBreakdown": {
            "cash": agg["cash"] or 0,
            "upi": agg["upi"] or 0,
            "online": agg["online"] or 0,
            "other": agg["other"] or 0,
        },
    }


def collection_snapshot_for_branch(branch_id, *, today, month_start) -> tuple[int, int]:
    """(collected_today_paise, collected_month_paise) via one aggregated query —
    replaces looping over up to 1000 payment rows in Python, which could also
    silently under-count a branch with more than 1000 payments in a month."""
    today_start = _utc_day_start(today)
    today_end = _utc_day_start(today + datetime.timedelta(days=1))
    month_start_dt = _utc_day_start(month_start)
    qs = Payment.objects.filter(
        invoice__branch_id=branch_id, status=PaymentStatus.CAPTURED, is_active=True,
    ).annotate(effective_date=Coalesce("captured_at", "created_at"))
    agg = qs.aggregate(
        today=Sum("amount_paise", filter=Q(effective_date__gte=today_start, effective_date__lt=today_end)),
        month=Sum("amount_paise", filter=Q(effective_date__gte=month_start_dt)),
    )
    return agg["today"] or 0, agg["month"] or 0
