"""Credit note interactors."""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from apps.fees.enums import CreditNoteStatus
from apps.fees.models import CreditNote
from apps.fees.queries.concession import create_credit_note, get_credit_note_for_update, update_credit_note
from apps.fees.queries.invoice import apply_amount_to_invoice, get_invoice_for_student


class CreateCreditNoteInteractor:
    """Creates a credit note request against a specific student/invoice."""

    def __init__(self, branch, student, invoice_id, amount_paise, reason, user):
        self.branch = branch
        self.student = student
        self.invoice_id = invoice_id
        self.amount_paise = amount_paise
        self.reason = reason
        self.user = user

    def execute(self) -> CreditNote:
        invoice = get_invoice_for_student(self.invoice_id, self.student.id)
        if invoice is None:
            raise ValidationError("Invoice not found for the given student.")
        if self.amount_paise <= 0:
            raise ValidationError("Credit note amount must be greater than zero.")
        if self.amount_paise > invoice.balance_paise:
            raise ValidationError("Credit note amount cannot exceed the outstanding invoice balance.")

        return create_credit_note(
            branch=self.branch, student=self.student, invoice=invoice,
            amount_paise=self.amount_paise, reason=self.reason,
            status=CreditNoteStatus.PENDING, user=self.user,
        )


class ApproveCreditNoteInteractor:
    """Approves/rejects a credit note; on approval credits the invoice ledger (EC-FEE-07)."""

    def __init__(self, credit_note_id, status, approver_user):
        self.credit_note_id = credit_note_id
        self.status = status
        self.approver_user = approver_user

    @transaction.atomic
    def execute(self) -> CreditNote:
        if self.status not in [CreditNoteStatus.APPROVED, CreditNoteStatus.REJECTED]:
            raise ValidationError("Invalid credit note status decision.")

        cn = get_credit_note_for_update(self.credit_note_id)
        if not cn:
            raise ValidationError("Credit note not found.")
        if cn.status != CreditNoteStatus.PENDING:
            raise ValidationError("Credit note has already been decided.")

        update_credit_note(cn, {
            "status": self.status, "approved_by": self.approver_user, "decided_at": timezone.now(),
        })

        if self.status == CreditNoteStatus.APPROVED:
            invoice = cn.invoice
            if not invoice:
                raise ValidationError("Credit note is not linked to an invoice.")
            amount = min(cn.amount_paise, invoice.balance_paise)
            if amount > 0:
                apply_amount_to_invoice(invoice, amount)

        return cn
