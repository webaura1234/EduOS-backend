"""Receipt interactors."""

from apps.fees.models import Receipt
from apps.fees.queries.receipt import get_receipt, list_receipts


def get_receipt_interactor(branch_id, receipt_id) -> Receipt | None:
    return get_receipt(branch_id, receipt_id)


def list_receipts_interactor(branch_id, student_id=None) -> list[Receipt]:
    return list_receipts(branch_id, student_id)
