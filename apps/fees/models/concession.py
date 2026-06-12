"""Concessions, credit notes, and the webhook idempotency log."""

from django.db import models

from apps.core.models import BaseModel
from apps.fees.enums import ConcessionStatus, CreditNoteStatus


class ConcessionRule(BaseModel):
    """A reusable discount/scholarship rule (F-137)."""

    branch = models.ForeignKey("organizations.Branch", on_delete=models.CASCADE, related_name="concession_rules")
    name = models.CharField(max_length=150)
    amount_paise = models.BigIntegerField(null=True, blank=True, help_text="Flat discount; null if percent-based.")
    percent = models.PositiveSmallIntegerField(null=True, blank=True, help_text="0–100; null if flat.")
    criteria = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "fees_concession_rule"
        verbose_name = "Concession Rule"
        verbose_name_plural = "Concession Rules"

    def __str__(self):
        return self.name


class ConcessionRequest(BaseModel):
    """A concession applied to a student, pending admin approval (F-137)."""

    branch = models.ForeignKey("organizations.Branch", on_delete=models.CASCADE, related_name="concession_requests")
    student = models.ForeignKey("admissions.StudentEnrollment", on_delete=models.CASCADE,
                                related_name="concession_requests")
    rule = models.ForeignKey(ConcessionRule, on_delete=models.SET_NULL, null=True, blank=True,
                             related_name="requests")
    amount_paise = models.BigIntegerField()
    status = models.CharField(max_length=10, choices=ConcessionStatus.choices, default=ConcessionStatus.PENDING)
    requested_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, related_name="+")
    approver = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)
    note = models.TextField(blank=True, default="")

    class Meta:
        db_table = "fees_concession_request"
        verbose_name = "Concession Request"
        verbose_name_plural = "Concession Requests"
        indexes = [models.Index(fields=["branch", "status"])]

    def __str__(self):
        return f"Concession {self.amount_paise} for {self.student_id} ({self.status})"


class CreditNote(BaseModel):
    """Retroactive scholarship credit, pending admin approval (F-151/EC-FEE-07)."""

    branch = models.ForeignKey("organizations.Branch", on_delete=models.CASCADE, related_name="credit_notes")
    student = models.ForeignKey("admissions.StudentEnrollment", on_delete=models.CASCADE, related_name="credit_notes")
    invoice = models.ForeignKey("fees.FeeInvoice", on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="credit_notes")
    amount_paise = models.BigIntegerField()
    reason = models.TextField(blank=True, default="")
    status = models.CharField(max_length=10, choices=CreditNoteStatus.choices, default=CreditNoteStatus.PENDING)
    approved_by = models.ForeignKey("accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "fees_credit_note"
        verbose_name = "Credit Note"
        verbose_name_plural = "Credit Notes"

    def __str__(self):
        return f"CreditNote {self.amount_paise} for {self.student_id} ({self.status})"


class WebhookEventLog(BaseModel):
    """Idempotency log for gateway webhooks (EC-FEE-02)."""

    event_id = models.CharField(max_length=120, unique=True)
    razorpay_payment_id = models.CharField(max_length=80, blank=True, default="", db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "fees_webhook_event_log"
        verbose_name = "Webhook Event Log"
        verbose_name_plural = "Webhook Event Logs"

    def __str__(self):
        return f"Webhook {self.event_id}"
