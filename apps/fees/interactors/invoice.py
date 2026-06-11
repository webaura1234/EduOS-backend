"""Invoice interactors."""

import datetime
from django.db import transaction

from apps.fees.enums import InvoiceStatus
from apps.fees.models import FeeInvoice
from apps.fees.queries.concession import list_approved_requests_for_student
from apps.fees.queries.invoice import (
    create_installment,
    create_invoice,
    create_invoice_line,
    invoice_exists_for_assignment,
)
from apps.fees.queries.structure import (
    billing_guardian_for_student,
    create_assignment,
    get_assignment_for_student_structure,
    students_in_batch,
)


@transaction.atomic
def generate_invoices_for_batch(*, branch, batch_id, academic_year, fee_structure, user=None) -> list[FeeInvoice]:
    """
    Generates invoices and installments for all active students in a batch who have assignments.
    If a student doesn't have an assignment, we create one using the structure snapshot.
    """
    students = students_in_batch(batch_id)
    invoices_created = []

    for student in students:
        # 1. Get or create assignment
        assignment = get_assignment_for_student_structure(student.id, fee_structure.id)
        if assignment is None:
            discount_lines = [
                {"request_id": str(req.id),
                 "label": req.rule.name if req.rule else "Concession",
                 "amount_paise": req.amount_paise}
                for req in list_approved_requests_for_student(student.id)
            ]
            assignment = create_assignment(
                student=student,
                fee_structure=fee_structure,
                structure_snapshot=fee_structure.components or [],
                discount_lines=discount_lines,
                user=user,
            )

        # Skip if an invoice already exists for this assignment
        if invoice_exists_for_assignment(assignment.id):
            continue

        # 2. Calculate invoice amounts
        components = assignment.structure_snapshot or []
        discount_lines = assignment.discount_lines or []
        total_components_paise = sum(int(c.get("amount_paise", 0)) for c in components)
        total_discount_paise = sum(int(d.get("amount_paise", 0)) for d in discount_lines)
        total_invoice_paise = max(total_components_paise - total_discount_paise, 0)

        # 3. Create the invoice — find billing guardian if the student has one.
        billing_guardian = billing_guardian_for_student(student)

        # Determine due date (use the latest due date among components, or today)
        due_dates = []
        for c in components:
            due_str = c.get("due_date")
            if due_str:
                due_dates.append(datetime.date.fromisoformat(due_str))
        
        due_date = max(due_dates) if due_dates else datetime.date.today()

        invoice = create_invoice(
            branch=branch,
            student=student,
            assignment=assignment,
            billing_guardian=billing_guardian,
            due_date=due_date,
            total_paise=total_invoice_paise,
            status=InvoiceStatus.PAID if total_invoice_paise == 0 else InvoiceStatus.DUE,
            user=user,
        )

        # 4. Create Invoice Lines
        for c in components:
            create_invoice_line(
                invoice=invoice,
                kind=c.get("kind", "other"),
                label=c.get("label", "Fee Component"),
                amount_paise=int(c.get("amount_paise", 0)),
                user=user,
            )

        # 5. Create Installments
        # Group components by installment_no
        installment_groups = {}
        for c in components:
            inst_no = int(c.get("installment_no", 1))
            installment_groups.setdefault(inst_no, []).append(c)

        # Calculate installment components totals
        installment_totals = {}
        installment_due_dates = {}
        for inst_no, inst_components in installment_groups.items():
            installment_totals[inst_no] = sum(int(c.get("amount_paise", 0)) for c in inst_components)
            # Due date for installment is the max of its components due dates
            inst_due_dates = [datetime.date.fromisoformat(c.get("due_date")) for c in inst_components if c.get("due_date")]
            installment_due_dates[inst_no] = max(inst_due_dates) if inst_due_dates else due_date

        # Distribute discount across installments proportionally
        # Formula: inst_discount = total_discount * (inst_total / total_components)
        remaining_discount = total_discount_paise
        inst_nos = sorted(installment_totals.keys())
        
        for idx, inst_no in enumerate(inst_nos):
            inst_components_total = installment_totals[inst_no]
            if total_components_paise > 0:
                if idx == len(inst_nos) - 1:
                    # Last one gets the remainder to avoid rounding loss
                    inst_discount = remaining_discount
                else:
                    inst_discount = (total_discount_paise * inst_components_total) // total_components_paise
                    remaining_discount -= inst_discount
            else:
                inst_discount = 0

            inst_amount = max(inst_components_total - inst_discount, 0)
            
            create_installment(
                invoice=invoice,
                sequence=inst_no,
                amount_paise=inst_amount,
                due_date=installment_due_dates[inst_no],
                status=InvoiceStatus.PAID if inst_amount == 0 else InvoiceStatus.DUE,
                user=user,
            )

        invoices_created.append(invoice)

    return invoices_created
