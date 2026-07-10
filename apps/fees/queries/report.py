"""Queries — collection/finance aggregates."""

from django.db.models import Sum

from apps.fees.enums import StudentConcessionStatus, RefundStatus
from apps.fees.models import FeeInvoice, Refund, StudentConcession


def invoice_totals(branch_id) -> tuple[int, int]:
    """(total_invoiced_paise, total_collected_paise) for a branch."""
    agg = FeeInvoice.objects.filter(branch_id=branch_id, is_active=True).aggregate(
        total_invoiced=Sum("total_paise"), total_collected=Sum("paid_paise")
    )
    return agg.get("total_invoiced") or 0, agg.get("total_collected") or 0


def total_refunded(branch_id) -> int:
    return Refund.objects.filter(
        payment__invoice__branch_id=branch_id, status=RefundStatus.PROCESSED, is_active=True
    ).aggregate(t=Sum("amount_paise")).get("t") or 0


def total_concessions(branch_id) -> int:
    return StudentConcession.objects.filter(
        branch_id=branch_id, status=StudentConcessionStatus.ACTIVE, is_active=True
    ).aggregate(t=Sum("amount_paise")).get("t") or 0
