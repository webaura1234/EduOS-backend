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


def collection_by_batch(branch_id) -> list[dict]:
    """Per-batch fee collection summary for export."""
    from django.db.models import Count
    from apps.admissions.models import StudentEnrollment

    rows = []
    batches = (
        StudentEnrollment.objects.filter(branch_id=branch_id, is_active=True)
        .values("batch_id", "batch__name")
        .annotate(student_count=Count("id"))
        .order_by("batch__name")
    )
    for b in batches:
        batch_id = b["batch_id"]
        if not batch_id:
            continue
        inv_qs = FeeInvoice.objects.filter(
            branch_id=branch_id,
            student__batch_id=batch_id,
            is_active=True,
        )
        agg = inv_qs.aggregate(
            total_invoiced=Sum("total_paise"),
            total_collected=Sum("paid_paise"),
            invoice_count=Count("id"),
        )
        invoiced = agg.get("total_invoiced") or 0
        collected = agg.get("total_collected") or 0
        rows.append({
            "batchId": str(batch_id),
            "batchName": b["batch__name"] or "",
            "studentCount": b["student_count"],
            "invoiceCount": agg.get("invoice_count") or 0,
            "totalInvoiced": round(invoiced / 100, 2),
            "totalCollected": round(collected / 100, 2),
            "totalPending": round(max(invoiced - collected, 0) / 100, 2),
        })
    return rows
