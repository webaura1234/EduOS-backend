"""Fee invoice, lines, and installments."""

from django.db import models

from apps.core.models import BaseModel
from apps.fees.enums import FeeComponentKind, InvoiceStatus


class FeeInvoice(BaseModel):
    """A demand notice for a student. total_paise may be 0 (full scholarship, F-148)."""

    branch = models.ForeignKey("organizations.Branch", on_delete=models.CASCADE, related_name="fee_invoices")
    student = models.ForeignKey("accounts.StudentProfile", on_delete=models.CASCADE, related_name="fee_invoices")
    assignment = models.ForeignKey("fees.StudentFeeAssignment", on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="invoices")
    billing_guardian = models.ForeignKey("accounts.GuardianProfile", on_delete=models.SET_NULL, null=True, blank=True,
                                         related_name="billed_invoices")
    due_date = models.DateField(null=True, blank=True)
    total_paise = models.BigIntegerField(default=0)
    paid_paise = models.BigIntegerField(default=0)
    status = models.CharField(max_length=15, choices=InvoiceStatus.choices, default=InvoiceStatus.DUE)

    class Meta:
        db_table = "fees_fee_invoice"
        verbose_name = "Fee Invoice"
        verbose_name_plural = "Fee Invoices"
        indexes = [models.Index(fields=["branch", "status", "due_date"])]

    def __str__(self):
        return f"Invoice {self.id} — {self.status} ({self.paid_paise}/{self.total_paise})"

    @property
    def balance_paise(self) -> int:
        return max(self.total_paise - self.paid_paise, 0)


class FeeInvoiceLine(BaseModel):
    """One line per fee component on an invoice."""

    invoice = models.ForeignKey(FeeInvoice, on_delete=models.CASCADE, related_name="lines")
    kind = models.CharField(max_length=15, choices=FeeComponentKind.choices, default=FeeComponentKind.TUITION)
    label = models.CharField(max_length=150)
    amount_paise = models.BigIntegerField(default=0)

    class Meta:
        db_table = "fees_fee_invoice_line"
        verbose_name = "Fee Invoice Line"
        verbose_name_plural = "Fee Invoice Lines"

    def __str__(self):
        return f"{self.label}: {self.amount_paise}"


class Installment(BaseModel):
    """An installment of an invoice (F-140)."""

    invoice = models.ForeignKey(FeeInvoice, on_delete=models.CASCADE, related_name="installments")
    sequence = models.PositiveSmallIntegerField()
    amount_paise = models.BigIntegerField(default=0)
    paid_paise = models.BigIntegerField(default=0)
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=15, choices=InvoiceStatus.choices, default=InvoiceStatus.DUE)

    class Meta:
        db_table = "fees_installment"
        verbose_name = "Installment"
        verbose_name_plural = "Installments"
        constraints = [
            models.UniqueConstraint(fields=["invoice", "sequence"], name="unique_installment_per_invoice"),
        ]

    def __str__(self):
        return f"Installment {self.sequence} of {self.invoice_id}"
