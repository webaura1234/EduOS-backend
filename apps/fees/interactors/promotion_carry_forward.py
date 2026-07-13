"""Fee assignment and opening-balance carry-forward for promotion execution."""

from __future__ import annotations

from apps.fees.enums import FeeComponentKind, InvoiceStatus, OpeningBalanceSource
from apps.fees.queries import invoice as invoice_q
from apps.fees.queries import structure as fees_q
from apps.fees.services.concession_sync import rebuild_assignment_discounts


def create_opening_balance_invoice(
    *,
    branch,
    enrollment,
    assignment,
    amount_paise: int,
    source_year,
    opening_balance_source,
    source_year_label: str,
    promotion_session=None,
    user=None,
):
    if amount_paise <= 0:
        return None
    invoice = invoice_q.create_invoice(
        branch=branch,
        student=enrollment,
        assignment=assignment,
        total_paise=amount_paise,
        status=InvoiceStatus.DUE,
        opening_balance_source_year=source_year,
        opening_balance_source=opening_balance_source,
        promotion_session=promotion_session,
        user=user,
    )
    invoice_q.create_invoice_line(
        invoice=invoice,
        kind=FeeComponentKind.OTHER,
        label=f"Prior Year Balance ({source_year_label})",
        amount_paise=amount_paise,
        user=user,
    )
    return invoice


def setup_promotion_fees(
    *,
    branch_id,
    branch,
    new_enrollment,
    fee_structure_id,
    source_enrollment_id,
    source_year,
    source_year_label: str,
    promotion_session=None,
    user=None,
) -> tuple[str | None, int]:
    """Create fee assignment, sync concessions, optional opening-balance invoice."""
    structure = fees_q.get_structure(branch_id, fee_structure_id)
    if not structure:
        raise ValueError("Fee structure not found.")

    assignment = fees_q.create_assignment(
        student=new_enrollment,
        fee_structure=structure,
        structure_snapshot=structure.components or [],
        discount_lines=[],
        user=user,
    )
    rebuild_assignment_discounts(assignment, user=user)

    opening = invoice_q.outstanding_balance_paise(source_enrollment_id) if source_enrollment_id else 0
    if opening > 0:
        opening_invoice = create_opening_balance_invoice(
            branch=branch,
            enrollment=new_enrollment,
            assignment=assignment,
            amount_paise=opening,
            source_year=source_year,
            opening_balance_source=OpeningBalanceSource.PROMOTION,
            source_year_label=source_year_label,
            promotion_session=promotion_session,
            user=user,
        )
        invoice_q.mark_invoices_carried_forward(
            source_enrollment_id, opening_invoice, user=user
        )
    return str(assignment.pk), opening
