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


class ConcessionStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class CreditNoteStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
