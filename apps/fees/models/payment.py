"""Payment, Receipt (gap-free), ReceiptCounter, Refund."""

from django.db import models

from apps.core.models import BaseModel
from apps.fees.enums import PaymentMethod, PaymentStatus, RefundStatus


class Payment(BaseModel):
    """A payment attempt against an invoice (online via Razorpay, or offline)."""

    invoice = models.ForeignKey("fees.FeeInvoice", on_delete=models.CASCADE, related_name="payments")
    amount_paise = models.BigIntegerField()
    method = models.CharField(max_length=15, choices=PaymentMethod.choices, default=PaymentMethod.RAZORPAY)
    status = models.CharField(max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.CREATED)

    razorpay_order_id = models.CharField(max_length=80, unique=True, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=80, unique=True, null=True, blank=True)
    payer = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="fee_payments")
    captured_at = models.DateTimeField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "fees_payment"
        verbose_name = "Payment"
        verbose_name_plural = "Payments"
        indexes = [
            models.Index(fields=["razorpay_payment_id"]),
            models.Index(fields=["invoice", "status"]),
        ]

    def __str__(self):
        return f"Payment {self.id} — {self.status} ({self.amount_paise})"


class ReceiptCounter(BaseModel):
    """Per-(branch, financial_year) counter; locked via select_for_update to keep receipts gap-free."""

    branch = models.ForeignKey("organizations.Branch", on_delete=models.CASCADE, related_name="receipt_counters")
    financial_year = models.CharField(max_length=10)
    last_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "fees_receipt_counter"
        verbose_name = "Receipt Counter"
        verbose_name_plural = "Receipt Counters"
        constraints = [
            models.UniqueConstraint(fields=["branch", "financial_year"], name="unique_receipt_counter"),
        ]


class Receipt(BaseModel):
    """Official receipt; sequence_number is gap-free per (branch, financial_year) (F-145/EC-FEE-09)."""

    branch = models.ForeignKey("organizations.Branch", on_delete=models.CASCADE, related_name="receipts")
    payment = models.OneToOneField(Payment, on_delete=models.CASCADE, related_name="receipt")
    sequence_number = models.PositiveIntegerField()
    financial_year = models.CharField(max_length=10)
    pdf_s3_key = models.CharField(max_length=500, blank=True, default="")
    issued_at = models.DateTimeField()

    class Meta:
        db_table = "fees_receipt"
        verbose_name = "Receipt"
        verbose_name_plural = "Receipts"
        constraints = [
            models.UniqueConstraint(fields=["branch", "financial_year", "sequence_number"],
                                    name="unique_receipt_seq_per_fy"),
        ]

    def __str__(self):
        return f"Receipt {self.financial_year}/{self.sequence_number}"

    @property
    def receipt_no(self) -> str:
        return f"{self.financial_year}/{self.sequence_number:05d}"


class Refund(BaseModel):
    """A refund against a payment (F-146)."""

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name="refunds")
    amount_paise = models.BigIntegerField()
    reason = models.TextField(blank=True, default="")
    status = models.CharField(max_length=15, choices=RefundStatus.choices, default=RefundStatus.REQUESTED)
    approved_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="approved_refunds")
    razorpay_refund_id = models.CharField(max_length=80, unique=True, null=True, blank=True)
    idempotency_key = models.CharField(max_length=120, unique=True)

    class Meta:
        db_table = "fees_refund"
        verbose_name = "Refund"
        verbose_name_plural = "Refunds"

    def __str__(self):
        return f"Refund {self.id} — {self.status} ({self.amount_paise})"
