"""Queries — Receipt and ReceiptCounter."""

from apps.fees.models import Receipt, ReceiptCounter


def get_receipt_counter(branch_id, financial_year) -> ReceiptCounter:
    """Gets or creates the ReceiptCounter for a branch/FY, locking the row for updates."""
    # Use select_for_update to lock the row in a transaction to avoid gap sequence issues.
    counter, created = ReceiptCounter.objects.select_for_update().get_or_create(
        branch_id=branch_id,
        financial_year=financial_year,
        defaults={"last_number": 0},
    )
    return counter


def next_receipt_number(counter: ReceiptCounter) -> int:
    """Increment and persist the locked counter; return the new gap-free number."""
    counter.last_number += 1
    counter.save(update_fields=["last_number", "updated_at"])
    return counter.last_number


def create_receipt(*, branch, payment, sequence_number, financial_year, issued_at, pdf_s3_key="", user=None) -> Receipt:
    return Receipt.objects.create(
        branch=branch,
        payment=payment,
        sequence_number=sequence_number,
        financial_year=financial_year,
        issued_at=issued_at,
        pdf_s3_key=pdf_s3_key,
        created_by=user,
        updated_by=user,
    )


def list_receipts(branch_id, student_id=None):
    qs = Receipt.objects.filter(branch_id=branch_id, is_active=True).select_related(
        "payment", "payment__invoice", "payment__invoice__student", "payment__invoice__student__student_profile__user"
    )
    if student_id:
        qs = qs.filter(payment__invoice__student_id=student_id)
    return qs.order_by("-issued_at")


def get_receipt(branch_id, receipt_id) -> Receipt | None:
    try:
        return Receipt.objects.select_related("payment", "payment__invoice").get(
            branch_id=branch_id, pk=receipt_id, is_active=True
        )
    except (Receipt.DoesNotExist, ValueError, TypeError):
        return None
