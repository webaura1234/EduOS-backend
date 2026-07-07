"""
Enumerations for the organizations app.

Centralised here so models, serializers, and services share one source of truth.
"""

from django.db import models


class InstitutionType(models.TextChoices):
    SCHOOL = "school", "School"
    COLLEGE = "college", "College"


class InstitutionStatus(models.TextChoices):
    TRIAL = "trial", "Trial"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    DEACTIVATED = "deactivated", "Deactivated"
    OFFBOARDING = "offboarding", "Offboarding"


class PlanType(models.TextChoices):
    STANDARD = "standard", "Standard ERP"
    AI = "ai", "AI ERP"


# Legacy tier slugs kept for data migrations and backward-compatible reads.
LEGACY_PLAN_TYPES = frozenset({"starter", "growth", "enterprise"})

LEGACY_TO_CURRENT_PLAN = {
    "starter": PlanType.STANDARD,
    "growth": PlanType.STANDARD,
    "enterprise": PlanType.AI,
}


class BillingStatus(models.TextChoices):
    TRIAL = "trial", "Trial"
    PAID = "paid", "Paid"
    OVERDUE = "overdue", "Overdue"
    CANCELLED = "cancelled", "Cancelled"


class StudentPlatformSubscriptionStatus(models.TextChoices):
    PAID = "paid", "Paid"
    UNPAID = "unpaid", "Unpaid"
    OVERDUE = "overdue", "Overdue"
    WAIVED = "waived", "Waived"


class QuotaResource(models.TextChoices):
    """Metered resources tracked per tenant (TenantQuota)."""
    STUDENTS = "students", "Students"
    STORAGE_BYTES = "storage_bytes", "Storage (bytes)"
    SMS_COUNT = "sms_count", "SMS count"
    AI_TOKENS = "ai_tokens", "AI tokens"
    API_CALLS = "api_calls", "API calls"


class QuotaPeriod(models.TextChoices):
    """Accounting window for a quota counter."""
    MONTH = "month", "Per month"
    TOTAL = "total", "Lifetime total"


class AttendanceMode(models.TextChoices):
    """How a tenant takes attendance."""
    DAY = "day", "Day-wise (one mark per student per day)"
    SESSION = "session", "Session-wise (one mark per class period)"


class SubscriptionPeriodStatus(models.TextChoices):
    """Lifecycle of an annual tenant subscription window."""
    ACTIVE = "active", "Active"
    GRACE = "grace", "Grace"
    EXPIRED = "expired", "Expired"
    CANCELLED = "cancelled", "Cancelled"


class LicenseInvoiceType(models.TextChoices):
    INITIAL = "initial", "Initial"
    TOP_UP = "top_up", "Top-up"
    RENEWAL = "renewal", "Renewal"


class LicenseInvoiceStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ISSUED = "issued", "Issued"
    PAID = "paid", "Paid"
    VOID = "void", "Void"


class LicensePaymentMode(models.TextChoices):
    CASH = "cash", "Cash"
    CHEQUE = "cheque", "Cheque"
    UPI = "upi", "UPI"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    ONLINE = "online", "Online"


class StudentLicenseStatus(models.TextChoices):
    UNLICENSED = "unlicensed", "Unlicensed"
    LICENSED = "licensed", "Licensed"


class LicenseEventType(models.TextChoices):
    STUDENT_ENROLLED = "student_enrolled", "Student enrolled"
    LICENSE_ASSIGNED = "license_assigned", "License assigned"
    PAYMENT_RECEIVED = "payment_received", "Payment received"
    INVOICE_GENERATED = "invoice_generated", "Invoice generated"
    STUDENT_WITHDRAWN = "student_withdrawn", "Student withdrawn"
    STUDENT_RESTORED = "student_restored", "Student restored"
    STUDENT_DELETED = "student_deleted", "Student deleted"
    STUDENT_TRANSFERRED = "student_transferred", "Student transferred"
    DUPLICATE_MERGED = "duplicate_merged", "Duplicate merged"
    SUBSCRIPTION_RENEWED = "subscription_renewed", "Subscription renewed"
    SUBSCRIPTION_GRACE = "subscription_grace", "Subscription in grace"
    SUBSCRIPTION_EXPIRED = "subscription_expired", "Subscription expired"
    PERIOD_EXTENDED = "period_extended", "Period extended"
    MANUAL_OVERRIDE = "manual_override", "Manual override"
