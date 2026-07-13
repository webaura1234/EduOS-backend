"""Enumerations for the fees app."""

from django.db import models


class FeeComponentKind(models.TextChoices):
    TUITION = "tuition", "Tuition"
    TRANSPORT = "transport", "Transport"
    HOSTEL = "hostel", "Hostel"
    EXAM = "exam", "Exam"
    OTHER = "other", "Other"


class InvoiceStatus(models.TextChoices):
    DUE = "due", "Due"
    PARTIAL = "partial", "Partial"
    PAID = "paid", "Paid"
    WRITTEN_OFF = "written_off", "Written off"


class CarryForwardState(models.TextChoices):
    NORMAL = "normal", "Normal"
    CARRIED_FORWARD = "carried_forward", "Carried forward"


class OpeningBalanceSource(models.TextChoices):
    PROMOTION = "promotion", "Academic Year Promotion"
    ROLLOVER = "rollover", "Academic Year Rollover"


class PaymentStatus(models.TextChoices):
    CREATED = "created", "Created"
    PENDING = "pending", "Pending"
    CAPTURED = "captured", "Captured"
    FAILED = "failed", "Failed"
    REFUNDED = "refunded", "Refunded"
    REQUIRES_REVIEW = "requires_review", "Requires review"


class PaymentMethod(models.TextChoices):
    RAZORPAY = "razorpay", "Razorpay"
    CASH = "cash", "Cash"
    CHEQUE = "cheque", "Cheque"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"


class RefundStatus(models.TextChoices):
    REQUESTED = "requested", "Requested"
    APPROVED = "approved", "Approved"
    PROCESSED = "processed", "Processed"
    FAILED = "failed", "Failed"


class StudentConcessionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    REVOKED = "revoked", "Revoked"
    EXPIRED = "expired", "Expired"


# Backward-compatible alias during migration period.
ConcessionStatus = StudentConcessionStatus


class CreditNoteStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class FeeStructureStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"
    ARCHIVED = "archived", "Archived"


class FeeHeadChargeType(models.TextChoices):
    MANDATORY = "mandatory", "Mandatory"
    OPTIONAL = "optional", "Optional"


class FeeHeadBillingType(models.TextChoices):
    ONE_TIME = "one_time", "One-time"
    RECURRING = "recurring", "Recurring"


class FeeHeadRefundType(models.TextChoices):
    REFUNDABLE = "refundable", "Refundable"
    NON_REFUNDABLE = "non_refundable", "Non-refundable"
