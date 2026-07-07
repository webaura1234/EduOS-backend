"""
AI credit service — plan gate + per-student balance enforcement.

Call ``require_ai_credits`` from future AI endpoints before invoking models.
"""

from __future__ import annotations

from django.db import transaction

from apps.accounts.models.user import Role
from apps.organizations.billing.ai_access import AiAccessDenied, require_ai_plan
from apps.organizations.models.ai_credits import (
    AiCreditTxnType,
    StudentAiCreditBalance,
    StudentAiCreditTxn,
)
from apps.organizations.plan_catalog import (
    DEFAULT_INCLUDED_AI_CREDITS_PER_STUDENT,
    normalize_plan,
)


class InsufficientAiCredits(AiAccessDenied):
    """Raised when a student has no remaining AI credits."""


def get_or_create_balance(*, student_user) -> StudentAiCreditBalance:
    row, _ = StudentAiCreditBalance.objects.get_or_create(
        student_user=student_user,
        defaults={"tenant_id": student_user.tenant_id, "balance": 0},
    )
    return row


def grant_initial_credits(*, student_user, amount: int | None = None, user=None) -> StudentAiCreditBalance:
    """Grant the AI-plan included credit allocation to a student (idempotent per grant key)."""
    require_ai_plan(student_user.tenant_id)
    grant_amount = amount if amount is not None else DEFAULT_INCLUDED_AI_CREDITS_PER_STUDENT
    if grant_amount <= 0:
        return get_or_create_balance(student_user=student_user)

    idempotency_key = f"initial-grant:{student_user.id}"
    if StudentAiCreditTxn.objects.filter(
        student_user=student_user,
        idempotency_key=idempotency_key,
    ).exists():
        return get_or_create_balance(student_user=student_user)

    return _apply_txn(
        student_user=student_user,
        amount=grant_amount,
        txn_type=AiCreditTxnType.GRANT,
        idempotency_key=idempotency_key,
        notes="Initial AI plan credit allocation",
        user=user,
    )


@transaction.atomic
def recharge_credits(
    *,
    student_user,
    amount: int,
    idempotency_key: str = "",
    notes: str = "",
    user=None,
) -> StudentAiCreditBalance:
    require_ai_plan(student_user.tenant_id)
    if amount <= 0:
        raise ValueError("Recharge amount must be positive.")
    return _apply_txn(
        student_user=student_user,
        amount=amount,
        txn_type=AiCreditTxnType.RECHARGE,
        idempotency_key=idempotency_key or f"recharge:{student_user.id}:{amount}",
        notes=notes or "AI credit recharge",
        user=user,
    )


@transaction.atomic
def consume_credits(
    *,
    student_user,
    amount: int,
    idempotency_key: str,
    notes: str = "",
    metadata: dict | None = None,
) -> StudentAiCreditBalance:
    """Consume credits for an AI action. Raises InsufficientAiCredits when balance is too low."""
    require_ai_plan(student_user.tenant_id)
    if amount <= 0:
        raise ValueError("Consumption amount must be positive.")
    if student_user.role != Role.STUDENT:
        raise AiAccessDenied("AI credits are tracked per student.")

    if idempotency_key and StudentAiCreditTxn.objects.filter(
        student_user=student_user,
        idempotency_key=idempotency_key,
    ).exists():
        return get_or_create_balance(student_user=student_user)

    balance_row = get_or_create_balance(student_user=student_user)
    if balance_row.balance < amount:
        raise InsufficientAiCredits(
            f"Insufficient AI credits ({balance_row.balance} available, {amount} required). "
            "Please recharge to continue using AI features."
        )

    return _apply_txn(
        student_user=student_user,
        amount=-amount,
        txn_type=AiCreditTxnType.CONSUME,
        idempotency_key=idempotency_key,
        notes=notes or "AI feature usage",
        metadata=metadata,
        user=None,
    )


def _apply_txn(
    *,
    student_user,
    amount: int,
    txn_type: str,
    idempotency_key: str = "",
    notes: str = "",
    metadata: dict | None = None,
    user=None,
) -> StudentAiCreditBalance:
    balance_row = (
        StudentAiCreditBalance.objects.select_for_update()
        .filter(student_user=student_user)
        .first()
    )
    if balance_row is None:
        balance_row = StudentAiCreditBalance.objects.create(
            student_user=student_user,
            tenant_id=student_user.tenant_id,
            balance=0,
        )
    new_balance = balance_row.balance + amount
    if new_balance < 0:
        raise InsufficientAiCredits("Insufficient AI credits.")
    balance_row.balance = new_balance
    balance_row.save(update_fields=["balance", "updated_at"])

    StudentAiCreditTxn.objects.create(
        student_user=student_user,
        tenant_id=student_user.tenant_id,
        txn_type=txn_type,
        amount=amount,
        balance_after=new_balance,
        idempotency_key=idempotency_key or "",
        notes=notes,
        metadata=metadata or {},
        created_by=user,
    )
    return balance_row


def student_ai_credit_summary(*, student_user) -> dict:
    """API-facing shape for future student AI credit UI."""
    tenant_plan = normalize_plan(
        getattr(getattr(student_user.tenant, "subscription", None), "plan", None)
        if student_user.tenant_id
        else None
    )
    balance_row = StudentAiCreditBalance.objects.filter(student_user=student_user).first()
    return {
        "plan": tenant_plan,
        "includesAi": tenant_plan == "ai",
        "balance": balance_row.balance if balance_row else 0,
        "includedCreditsPerStudent": (
            DEFAULT_INCLUDED_AI_CREDITS_PER_STUDENT if tenant_plan == "ai" else 0
        ),
    }
