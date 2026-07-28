"""
License allocator — the single write path for non-recyclable student licenses.

Rules enforced here:
  - A license, once assigned (``licensed_at`` set), is consumed forever.
    Nothing in this module ever clears ``licensed_at`` or decrements
    ``licenses_consumed``.
  - New students auto-consume a license when the tenant still has unused
    purchased capacity; otherwise they become ``unlicensed``.
  - Payments convert the OLDEST unlicensed students first (FIFO by
    ``enrolled_at``). Partial payments convert exactly ``licenses_granted``.
  - Renewal is billed on total consumed licenses, never active headcount.

All entry points refresh the materialized ``TenantLicenseSummary`` so
dashboards read counters, not table scans.
"""

from __future__ import annotations

import datetime

from django.db import transaction
from django.db.models import F, Sum
from django.utils import timezone

from apps.organizations.billing.platform_pricing import unit_price_for_tenant
from apps.organizations.enums import (
    LicenseEventType,
    LicenseInvoiceStatus,
    LicenseInvoiceType,
    StudentLicenseStatus,
    SubscriptionPeriodStatus,
)
from apps.organizations.models import (
    LicenseEvent,
    LicenseInvoice,
    LicensePayment,
    StudentLicense,
    TenantLicenseSummary,
    TenantSubscriptionPeriod,
)

GRACE_DAYS = 30


# ── Period helpers ────────────────────────────────────────────────────────────

def default_period_dates(on_date: datetime.date | None = None) -> tuple[datetime.date, datetime.date]:
    """Indian financial/academic year window: Apr 1 → Mar 31."""
    today = on_date or timezone.localdate()
    year = today.year if today.month >= 4 else today.year - 1
    return datetime.date(year, 4, 1), datetime.date(year + 1, 3, 31)


def get_current_period(tenant_id) -> TenantSubscriptionPeriod | None:
    return (
        TenantSubscriptionPeriod.objects.filter(
            tenant_id=tenant_id,
            status__in=[SubscriptionPeriodStatus.ACTIVE, SubscriptionPeriodStatus.GRACE],
            is_active=True,
        )
        .order_by("-start_date")
        .first()
    )


def ensure_period(tenant, *, start=None, end=None, user=None) -> TenantSubscriptionPeriod:
    """Return the tenant's current period, creating a default one if missing."""
    period = get_current_period(tenant.pk)
    if period:
        return period
    d_start, d_end = default_period_dates()
    period = TenantSubscriptionPeriod.objects.create(
        tenant=tenant,
        start_date=start or d_start,
        end_date=end or d_end,
        price_per_student_inr=unit_price_for_tenant(tenant.pk),
        created_by=user,
        updated_by=user,
    )
    sync_plan_valid_until(period)
    return period


def sync_plan_valid_until(period: TenantSubscriptionPeriod) -> None:
    """Keep the legacy PlanSubscription renewal date in step with the licensing
    period so existing plan screens (renewsAt) stay correct."""
    from apps.organizations.models import PlanSubscription

    next_due = timezone.make_aware(
        datetime.datetime.combine(period.end_date, datetime.time(23, 59, 59)),
    )
    PlanSubscription.objects.filter(tenant=period.tenant).update(
        valid_until=period.end_date, next_due_at=next_due,
    )


def extend_period(period: TenantSubscriptionPeriod, new_end: datetime.date, *, user=None) -> TenantSubscriptionPeriod:
    """Platform Owner extends one school's window (e.g. to end of June)."""
    period.end_date = new_end
    if period.status == SubscriptionPeriodStatus.GRACE:
        period.status = SubscriptionPeriodStatus.ACTIVE
        period.grace_ends_at = None
    period.updated_by = user
    period.save(update_fields=["end_date", "status", "grace_ends_at", "updated_by", "updated_at"])
    sync_plan_valid_until(period)
    LicenseEvent.objects.create(
        tenant=period.tenant,
        event_type=LicenseEventType.PERIOD_EXTENDED,
        detail=f"Subscription extended to {new_end.isoformat()}",
        created_by=user,
    )
    return period


# ── Summary ───────────────────────────────────────────────────────────────────

def _get_summary(tenant) -> TenantLicenseSummary:
    summary, _ = TenantLicenseSummary.objects.get_or_create(tenant=tenant)
    return summary


def refresh_summary(tenant) -> TenantLicenseSummary:
    """Recompute counters from source tables (used by backfills and repair)."""
    from django.db.models import Q

    from apps.accounts.models.profile import AcademicStatus

    purchased = (
        LicensePayment.objects.filter(tenant=tenant, is_active=True)
        .aggregate(total=Sum("licenses_granted"))["total"] or 0
    )
    consumed = StudentLicense.objects.filter(
        tenant=tenant, licensed_at__isnull=False,
    ).count()
    # Match payment FIFO queue: active users who are unlicensed. Include students
    # without a profile (common in tests / early onboarding); exclude known
    # non-active academic statuses when a profile exists.
    unlicensed_active = StudentLicense.objects.filter(
        tenant=tenant,
        license_status=StudentLicenseStatus.UNLICENSED,
        student_user__is_active=True,
    ).filter(
        Q(student_user__student_profile__isnull=True)
        | Q(student_user__student_profile__academic_status=AcademicStatus.ACTIVE),
    ).count()
    price = unit_price_for_tenant(tenant.pk)

    summary = _get_summary(tenant)
    summary.licenses_purchased = purchased
    summary.licenses_consumed = consumed
    summary.unlicensed_active_count = unlicensed_active
    summary.pending_amount_inr = unlicensed_active * price
    summary.current_period = get_current_period(tenant.pk)
    summary.save()

    from apps.organizations.billing.storage_quota import sync_storage_limit_for_tenant

    sync_storage_limit_for_tenant(tenant)
    return summary


# ── Allocation core ───────────────────────────────────────────────────────────

def _assign_license(license_row: StudentLicense, *, payment=None, period=None, user=None) -> None:
    """Set licensed_at exactly once. Never called on an already-licensed row."""
    now = timezone.now()
    license_row.license_status = StudentLicenseStatus.LICENSED
    license_row.licensed_at = now
    if payment is not None:
        license_row.license_payment = payment
    if period is not None:
        license_row.subscription_period = period
    license_row.updated_by = user
    license_row.save(update_fields=[
        "license_status", "licensed_at", "license_payment",
        "subscription_period", "updated_by", "updated_at",
    ])
    LicenseEvent.objects.create(
        tenant=license_row.tenant,
        student_user=license_row.student_user,
        event_type=LicenseEventType.LICENSE_ASSIGNED,
        detail="License consumed (permanent).",
        payment=payment,
        created_by=user,
    )


@transaction.atomic
def on_student_enrolled(student_user, *, user=None) -> StudentLicense:
    """Create (or return) the student's license row; auto-license if the tenant
    still has unused purchased capacity. NEVER blocks enrollment."""
    tenant = student_user.tenant
    existing = StudentLicense.objects.filter(student_user=student_user).first()
    if existing:
        # Restored / re-enrolled student: license status is permanent (Case 8).
        if existing.branch_id != student_user.branch_id:
            existing.branch_id = student_user.branch_id
            existing.save(update_fields=["branch_id", "updated_at"])
        return existing

    period = ensure_period(tenant, user=user)
    row = StudentLicense.objects.create(
        tenant=tenant,
        branch_id=student_user.branch_id,
        student_user=student_user,
        student_name=student_user.full_name or "",
        enrolled_at=timezone.now(),
        subscription_period=period,
        created_by=user,
        updated_by=user,
    )
    LicenseEvent.objects.create(
        tenant=tenant,
        student_user=student_user,
        event_type=LicenseEventType.STUDENT_ENROLLED,
        detail="Student enrolled; license row created.",
        created_by=user,
    )

    summary = (
        TenantLicenseSummary.objects.select_for_update()
        .get_or_create(tenant=tenant)[0]
    )
    if summary.licenses_consumed < summary.licenses_purchased:
        _assign_license(row, period=period, user=user)
        summary.licenses_consumed = F("licenses_consumed") + 1
        summary.save(update_fields=["licenses_consumed", "updated_at"])
    else:
        summary.unlicensed_active_count = F("unlicensed_active_count") + 1
        summary.pending_amount_inr = (
            F("pending_amount_inr") + unit_price_for_tenant(tenant.pk)
        )
        summary.save(update_fields=["unlicensed_active_count", "pending_amount_inr", "updated_at"])
    return row


@transaction.atomic
def record_payment(
    tenant,
    *,
    licenses_granted: int,
    amount_inr: int,
    payment_mode: str,
    reference_number: str = "",
    paid_at: datetime.date | None = None,
    notes: str = "",
    idempotency_key: str | None = None,
    invoice: LicenseInvoice | None = None,
    branch_id=None,
    user=None,
) -> LicensePayment:
    """Record an offline payment and FIFO-convert unlicensed students.

    Partial payments (Case 6) convert exactly ``licenses_granted`` students,
    oldest ``enrolled_at`` first. When ``branch_id`` is set, only students in
    that branch are eligible for conversion.
    """
    if licenses_granted <= 0:
        raise ValueError("licenses_granted must be positive.")

    branch = None
    if branch_id is not None:
        from apps.organizations.models import Branch

        branch = Branch.objects.filter(pk=branch_id, tenant=tenant, is_active=True).first()
        if branch is None:
            raise ValueError("Branch not found for this school.")

    if idempotency_key:
        existing = LicensePayment.objects.filter(idempotency_key=idempotency_key).first()
        if existing:
            return existing

    period = ensure_period(tenant, user=user)
    payment = LicensePayment.objects.create(
        tenant=tenant,
        branch=branch,
        invoice=invoice,
        licenses_granted=licenses_granted,
        amount_inr=amount_inr,
        payment_mode=payment_mode,
        reference_number=reference_number,
        paid_at=paid_at or timezone.localdate(),
        recorded_by=user,
        notes=notes,
        idempotency_key=idempotency_key or None,
        created_by=user,
        updated_by=user,
    )
    branch_note = f" for {branch.name}" if branch else ""
    LicenseEvent.objects.create(
        tenant=tenant,
        event_type=LicenseEventType.PAYMENT_RECEIVED,
        detail=(
            f"Payment ₹{amount_inr} for {licenses_granted} license(s){branch_note} "
            f"via {payment_mode}."
        ),
        payment=payment,
        created_by=user,
    )
    if invoice and invoice.status != LicenseInvoiceStatus.PAID:
        invoice.status = LicenseInvoiceStatus.PAID
        invoice.save(update_fields=["status", "updated_at"])

    # FIFO conversion — oldest unlicensed first, optionally branch-scoped.
    queue_qs = StudentLicense.objects.select_for_update(skip_locked=True).filter(
        tenant=tenant,
        license_status=StudentLicenseStatus.UNLICENSED,
        student_user__is_active=True,
    )
    if branch_id is not None:
        queue_qs = queue_qs.filter(branch_id=branch_id)
    queue = list(queue_qs.order_by("enrolled_at")[:licenses_granted])
    for row in queue:
        _assign_license(row, payment=payment, period=period, user=user)

    converted = len(queue)
    price = unit_price_for_tenant(tenant.pk)
    summary = (
        TenantLicenseSummary.objects.select_for_update()
        .get_or_create(tenant=tenant)[0]
    )
    summary.licenses_purchased = F("licenses_purchased") + licenses_granted
    summary.licenses_consumed = F("licenses_consumed") + converted
    summary.unlicensed_active_count = F("unlicensed_active_count") - converted
    summary.pending_amount_inr = F("pending_amount_inr") - (converted * price)
    summary.save(update_fields=[
        "licenses_purchased", "licenses_consumed",
        "unlicensed_active_count", "pending_amount_inr", "updated_at",
    ])

    from apps.organizations.billing.billing_refresh import refresh_tenant_billing
    from apps.organizations.billing.storage_quota import sync_storage_limit_for_tenant

    refresh_tenant_billing(tenant.pk, user=user)
    sync_storage_limit_for_tenant(tenant)
    return payment


# ── Invoices ──────────────────────────────────────────────────────────────────

@transaction.atomic
def generate_invoice(
    tenant,
    *,
    invoice_type: str,
    licenses_count: int | None = None,
    notes: str = "",
    user=None,
) -> LicenseInvoice:
    """Create an invoice. For renewals the count is TOTAL consumed licenses."""
    period = ensure_period(tenant, user=user)
    price = unit_price_for_tenant(tenant.pk)

    if invoice_type == LicenseInvoiceType.RENEWAL:
        summary = _get_summary(tenant)
        count = summary.licenses_consumed
    else:
        if not licenses_count or licenses_count <= 0:
            raise ValueError("licenses_count is required for non-renewal invoices.")
        count = licenses_count

    invoice = LicenseInvoice.objects.create(
        tenant=tenant,
        subscription_period=period,
        invoice_type=invoice_type,
        licenses_count=count,
        unit_price_inr=price,
        amount_inr=count * price,
        status=LicenseInvoiceStatus.ISSUED,
        issued_at=timezone.now(),
        notes=notes,
        created_by=user,
        updated_by=user,
    )
    LicenseEvent.objects.create(
        tenant=tenant,
        event_type=LicenseEventType.INVOICE_GENERATED,
        detail=f"{invoice_type} invoice: {count} × ₹{price} = ₹{invoice.amount_inr}",
        created_by=user,
    )
    return invoice


def run_renewal_invoice_pipeline(
    *,
    within_days: int = 60,
    dry_run: bool = False,
    user=None,
) -> dict:
    """Issue RENEWAL invoices for periods ending soon (licenses_consumed × net unit).

    Idempotent: skips tenants that already have an ISSUED renewal invoice on the
    current period. Ensures a following subscription period exists once the
    current window has ended (does not recreate StudentLicense rows).
    """
    today = timezone.localdate()
    cutoff = today + datetime.timedelta(days=within_days)
    generated = 0
    skipped = 0
    ensured_periods = 0

    periods = list(
        TenantSubscriptionPeriod.objects.filter(
            status__in=[SubscriptionPeriodStatus.ACTIVE, SubscriptionPeriodStatus.GRACE],
            end_date__gte=today,
            end_date__lte=cutoff,
            is_active=True,
        ).select_related("tenant")
    )

    for period in periods:
        summary = _get_summary(period.tenant)
        if summary.licenses_consumed <= 0:
            skipped += 1
            continue

        already = LicenseInvoice.objects.filter(
            tenant=period.tenant,
            subscription_period=period,
            invoice_type=LicenseInvoiceType.RENEWAL,
            status=LicenseInvoiceStatus.ISSUED,
            is_active=True,
        ).exists()
        if already:
            skipped += 1
            continue

        if dry_run:
            generated += 1
            continue

        generate_invoice(
            period.tenant,
            invoice_type=LicenseInvoiceType.RENEWAL,
            notes="Auto-generated renewal invoice (period ending soon).",
            user=user,
        )
        generated += 1

        if period.end_date < today and get_current_period(period.tenant_id) is None:
            ensure_period(period.tenant, user=user)
            ensured_periods += 1

    return {
        "generated": generated,
        "skipped": skipped,
        "ensuredPeriods": ensured_periods,
    }


# ── Lifecycle events that do NOT release licenses ─────────────────────────────

def on_student_lifecycle_event(student_user, event_type: str, *, detail: str = "", user=None) -> None:
    """Record withdraw/restore/delete/transfer events. License stays consumed.

    Only the unlicensed-active counter moves (an unlicensed student who leaves
    no longer owes a license fee)."""
    row = StudentLicense.objects.filter(student_user=student_user).first()
    if row is None:
        return
    LicenseEvent.objects.create(
        tenant=row.tenant,
        student_user=student_user,
        event_type=event_type,
        detail=detail,
        created_by=user,
    )
    if row.license_status == StudentLicenseStatus.UNLICENSED and event_type in (
        LicenseEventType.STUDENT_WITHDRAWN,
        LicenseEventType.STUDENT_DELETED,
    ):
        price = unit_price_for_tenant(row.tenant_id)
        TenantLicenseSummary.objects.filter(tenant=row.tenant).update(
            unlicensed_active_count=F("unlicensed_active_count") - 1,
            pending_amount_inr=F("pending_amount_inr") - price,
        )


# ── Reads ─────────────────────────────────────────────────────────────────────

def get_summary_dict(tenant) -> dict:
    summary = _get_summary(tenant)
    period = summary.current_period or get_current_period(tenant.pk)
    price = unit_price_for_tenant(tenant.pk)
    return {
        "licensesPurchased": summary.licenses_purchased,
        "licensesConsumed": summary.licenses_consumed,
        "unlicensedStudents": summary.unlicensed_active_count,
        "pendingAmountInr": summary.pending_amount_inr,
        "unitPriceInr": price,
        "subscription": {
            "startDate": period.start_date.isoformat() if period else None,
            "endDate": period.end_date.isoformat() if period else None,
            "status": period.status if period else None,
            "graceEndsAt": (
                period.grace_ends_at.isoformat()
                if period and period.grace_ends_at else None
            ),
        },
    }


def run_expiry_pipeline(*, user=None) -> dict:
    """Move periods past end_date into grace, and past grace into expired."""
    today = timezone.localdate()
    moved_to_grace = 0
    expired = 0

    for period in TenantSubscriptionPeriod.objects.filter(
        status=SubscriptionPeriodStatus.ACTIVE, end_date__lt=today, is_active=True,
    ).select_related("tenant"):
        period.status = SubscriptionPeriodStatus.GRACE
        period.grace_ends_at = period.end_date + datetime.timedelta(days=GRACE_DAYS)
        period.save(update_fields=["status", "grace_ends_at", "updated_at"])
        LicenseEvent.objects.create(
            tenant=period.tenant,
            event_type=LicenseEventType.SUBSCRIPTION_GRACE,
            detail=f"Subscription entered grace (until {period.grace_ends_at.isoformat()}).",
            created_by=user,
        )
        moved_to_grace += 1

    for period in TenantSubscriptionPeriod.objects.filter(
        status=SubscriptionPeriodStatus.GRACE,
        grace_ends_at__lt=today,
        is_active=True,
    ).select_related("tenant"):
        period.status = SubscriptionPeriodStatus.EXPIRED
        period.save(update_fields=["status", "updated_at"])
        LicenseEvent.objects.create(
            tenant=period.tenant,
            event_type=LicenseEventType.SUBSCRIPTION_EXPIRED,
            detail="Subscription expired after grace; student restrictions applied.",
            created_by=user,
        )
        expired += 1

    return {"movedToGrace": moved_to_grace, "expired": expired}
