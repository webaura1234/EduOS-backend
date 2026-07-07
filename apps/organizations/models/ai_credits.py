"""
Per-student AI credit ledger — future-proof metering for AI ERP.

Credits are granted on enrollment / plan upgrade and consumed by AI endpoints.
Schools can recharge when a student's balance is exhausted.
"""

from django.db import models

from apps.core.models import BaseModel


class AiCreditTxnType(models.TextChoices):
    GRANT = "grant", "Grant"
    CONSUME = "consume", "Consume"
    RECHARGE = "recharge", "Recharge"
    ADMIN_ADJUST = "admin_adjust", "Admin adjust"
    PERIOD_RESET = "period_reset", "Period reset"


class StudentAiCreditBalance(BaseModel):
    """Current AI credit balance for one student user."""

    student_user = models.OneToOneField(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="ai_credit_balance",
    )
    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="student_ai_credit_balances",
    )
    balance = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "organizations_student_ai_credit_balance"
        verbose_name = "Student AI credit balance"
        verbose_name_plural = "Student AI credit balances"
        indexes = [
            models.Index(fields=["tenant"]),
        ]

    def __str__(self):
        return f"{self.student_user_id} — {self.balance} credits"


class StudentAiCreditTxn(BaseModel):
    """Immutable ledger entry for AI credit movements."""

    student_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="ai_credit_txns",
    )
    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="student_ai_credit_txns",
    )
    txn_type = models.CharField(max_length=20, choices=AiCreditTxnType.choices, db_index=True)
    amount = models.IntegerField(
        help_text="Positive for grants/recharges; negative for consumption.",
    )
    balance_after = models.PositiveIntegerField()
    idempotency_key = models.CharField(max_length=128, blank=True, default="", db_index=True)
    notes = models.CharField(max_length=255, blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "organizations_student_ai_credit_txn"
        ordering = ["-created_at"]
        verbose_name = "Student AI credit transaction"
        verbose_name_plural = "Student AI credit transactions"
        constraints = [
            models.UniqueConstraint(
                fields=["student_user", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="unique_ai_credit_idempotency_per_student",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "student_user", "-created_at"]),
        ]

    def __str__(self):
        return f"{self.txn_type} {self.amount} → {self.balance_after}"
