"""
Platform licensing — non-recyclable per-student licenses (₹499/student/year default).

Business rules:
  - One paid license is consumed forever by one student; it is NEVER released
    when the student withdraws, graduates, transfers, or is deleted.
  - Admissions are never blocked; students admitted beyond the purchased count
    become "unlicensed" until the Platform Owner records a payment.
  - Payments convert the OLDEST unlicensed students first (FIFO by enrolled_at).
  - Renewal is billed on total licenses consumed, not current active headcount.

Models:
  - TenantSubscriptionPeriod → annual access window per tenant (custom dates OK)
  - TenantLicensePricing     → optional per-tenant price override
  - LicenseInvoice           → initial / top-up / renewal invoices
  - LicensePayment           → immutable offline payment ledger
  - StudentLicense           → one row per student user; licensed_at is write-once
  - LicenseEvent             → append-only licensing history
  - TenantLicenseSummary     → materialized counters for dashboards
"""

from django.db import models

from apps.core.models import BaseModel
from apps.organizations.enums import (
    LicenseEventType,
    LicenseInvoiceStatus,
    LicenseInvoiceType,
    LicensePaymentMode,
    StudentLicenseStatus,
    SubscriptionPeriodStatus,
)

DEFAULT_LICENSE_PRICE_INR = 499


class TenantSubscriptionPeriod(BaseModel):
    """One annual subscription window for a tenant. Dates are per-tenant
    (Apr–Mar by default, but a school may run Jul–Jun etc.)."""

    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="subscription_periods",
    )
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=SubscriptionPeriodStatus.choices,
        default=SubscriptionPeriodStatus.ACTIVE,
        db_index=True,
    )
    price_per_student_inr = models.PositiveIntegerField(default=DEFAULT_LICENSE_PRICE_INR)
    grace_ends_at = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "organizations_tenant_subscription_period"
        ordering = ["-start_date"]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["end_date", "status"]),
        ]

    def __str__(self):
        return f"{self.tenant_id} {self.start_date}→{self.end_date} ({self.status})"


class TenantLicensePricing(BaseModel):
    """Optional per-tenant override of the list price."""

    tenant = models.OneToOneField(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="license_pricing",
    )
    price_per_student_inr = models.PositiveIntegerField(default=DEFAULT_LICENSE_PRICE_INR)
    effective_from = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "organizations_tenant_license_pricing"

    def __str__(self):
        return f"{self.tenant_id} @ ₹{self.price_per_student_inr}/student"


class LicenseInvoice(BaseModel):
    """An invoice for student licenses (initial purchase, top-up, or renewal)."""

    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="license_invoices",
    )
    subscription_period = models.ForeignKey(
        TenantSubscriptionPeriod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="invoices",
    )
    invoice_type = models.CharField(
        max_length=10, choices=LicenseInvoiceType.choices, default=LicenseInvoiceType.TOP_UP,
    )
    licenses_count = models.PositiveIntegerField()
    unit_price_inr = models.PositiveIntegerField(default=DEFAULT_LICENSE_PRICE_INR)
    amount_inr = models.PositiveIntegerField()
    status = models.CharField(
        max_length=10,
        choices=LicenseInvoiceStatus.choices,
        default=LicenseInvoiceStatus.ISSUED,
        db_index=True,
    )
    issued_at = models.DateTimeField(null=True, blank=True)
    due_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "organizations_license_invoice"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "status"])]

    def __str__(self):
        return f"{self.invoice_type} ×{self.licenses_count} = ₹{self.amount_inr} ({self.status})"


class LicensePayment(BaseModel):
    """Immutable ledger row for a license purchase recorded by the Platform Owner.

    ``licenses_granted`` is the authoritative purchase count — the FIFO
    allocator converts that many unlicensed students on save.
    """

    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="license_payments",
    )
    invoice = models.ForeignKey(
        LicenseInvoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="payments",
    )
    # When set, FIFO allocation is scoped to this branch only (audit trail).
    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="license_payments",
    )
    licenses_granted = models.PositiveIntegerField()
    amount_inr = models.PositiveIntegerField()
    payment_mode = models.CharField(
        max_length=20, choices=LicensePaymentMode.choices, default=LicensePaymentMode.CASH,
    )
    reference_number = models.CharField(max_length=100, blank=True, default="")
    paid_at = models.DateField()
    recorded_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    notes = models.TextField(blank=True, default="")
    idempotency_key = models.CharField(max_length=100, unique=True, null=True, blank=True)

    class Meta:
        db_table = "organizations_license_payment"
        ordering = ["-paid_at", "-created_at"]
        indexes = [models.Index(fields=["tenant", "paid_at"])]

    def __str__(self):
        return f"{self.tenant_id} +{self.licenses_granted} licenses ₹{self.amount_inr}"


class StudentLicense(BaseModel):
    """One row per student user — the license record.

    ``licensed_at`` is WRITE-ONCE. Once a student consumes a license it is
    permanently consumed; withdrawal/deletion/graduation never clears it.
    ``enrolled_at`` orders the FIFO queue for auto-allocation.
    """

    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="student_licenses",
    )
    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_licenses",
    )
    # SET_NULL, not CASCADE: a consumed license outlives its student. Hard
    # deleting a student must never erase the consumption record (Case 4).
    student_user = models.OneToOneField(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_license",
    )
    student_name = models.CharField(max_length=255, blank=True, default="")
    enrolled_at = models.DateTimeField(db_index=True)
    license_status = models.CharField(
        max_length=15,
        choices=StudentLicenseStatus.choices,
        default=StudentLicenseStatus.UNLICENSED,
        db_index=True,
    )
    licensed_at = models.DateTimeField(null=True, blank=True)
    license_payment = models.ForeignKey(
        LicensePayment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="licensed_students",
    )
    subscription_period = models.ForeignKey(
        TenantSubscriptionPeriod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_licenses",
    )

    class Meta:
        db_table = "organizations_student_license"
        indexes = [
            models.Index(fields=["tenant", "license_status", "enrolled_at"]),
            models.Index(fields=["branch", "license_status"]),
        ]

    def __str__(self):
        return f"{self.student_user_id} ({self.license_status})"


class LicenseEvent(BaseModel):
    """Append-only licensing history for audit and troubleshooting."""

    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="license_events",
    )
    student_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    event_type = models.CharField(max_length=30, choices=LicenseEventType.choices, db_index=True)
    detail = models.TextField(blank=True, default="")
    payment = models.ForeignKey(
        LicensePayment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )

    class Meta:
        db_table = "organizations_license_event"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["tenant", "event_type"])]

    def __str__(self):
        return f"{self.event_type} @ {self.tenant_id}"


class TenantLicenseSummary(BaseModel):
    """Materialized per-tenant counters — refreshed by the allocator on every
    enroll / payment so dashboards never scan the license table."""

    tenant = models.OneToOneField(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="license_summary",
    )
    licenses_purchased = models.PositiveIntegerField(default=0)
    licenses_consumed = models.PositiveIntegerField(default=0)
    unlicensed_active_count = models.PositiveIntegerField(default=0)
    pending_amount_inr = models.PositiveIntegerField(default=0)
    current_period = models.ForeignKey(
        TenantSubscriptionPeriod,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "organizations_tenant_license_summary"

    def __str__(self):
        return (
            f"{self.tenant_id}: purchased={self.licenses_purchased} "
            f"consumed={self.licenses_consumed} unlicensed={self.unlicensed_active_count}"
        )
