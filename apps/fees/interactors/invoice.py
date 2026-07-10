"""Invoice interactors."""

import datetime
from django.db import transaction

from apps.accounts.models.guardian import StudentGuardianLink
from apps.fees.enums import InvoiceStatus, StudentConcessionStatus
from apps.fees.models import (
    FeeInvoice,
    FeeInvoiceLine,
    Installment,
    StudentConcession,
    StudentFeeAssignment,
)
from apps.fees.helpers.concession import discount_line_for_request
from apps.fees.queries.structure import students_in_batch


def _billing_guardian_map(students) -> dict:
    """student.user_id -> GuardianProfile, for every student's primary portal
    guardian, in one query instead of one per student (mirrors
    ``billing_guardian_for_student``'s "first portal-access link" semantics)."""
    user_ids = [s.user_id for s in students]
    guardian_by_user_id: dict = {}
    links = StudentGuardianLink.objects.filter(
        student_id__in=user_ids, has_portal_access=True, is_active=True,
    ).select_related("guardian__guardian_profile")
    for link in links:
        guardian_by_user_id.setdefault(link.student_id, link)

    result = {}
    for sid, link in guardian_by_user_id.items():
        try:
            result[sid] = link.guardian.guardian_profile
        except AttributeError:
            result[sid] = None
    return result


@transaction.atomic
def generate_invoices_for_batch(*, branch, batch_id, academic_year, fee_structure, user=None) -> list[FeeInvoice]:
    """
    Generates invoices and installments for all active students in a batch who have assignments.
    If a student doesn't have an assignment, we create one using the structure snapshot.

    Batched to a fixed number of queries regardless of batch size (assignment
    lookup/creation, invoice-exists check, billing guardian, and all invoice
    lines/installments are each one bulk query) instead of ~6+ queries per
    student plus one INSERT per line/installment — this runs for every batch,
    every term, every tenant, and batches can run into the thousands of students.
    """
    students = list(students_in_batch(batch_id))
    if not students:
        return []
    student_ids = [s.id for s in students]
    student_by_id = {s.id: s for s in students}

    # 1. Existing (student, structure) assignments, in one query.
    assignment_by_student: dict = {
        a.student_id: a
        for a in StudentFeeAssignment.objects.filter(
            student_id__in=student_ids, fee_structure_id=fee_structure.id, is_active=True,
        )
    }

    # 2. Active concessions for students who still need a new assignment.
    missing_ids = [sid for sid in student_ids if sid not in assignment_by_student]
    active_by_student: dict = {}
    if missing_ids:
        for req in StudentConcession.objects.filter(
            student_id__in=missing_ids, status=StudentConcessionStatus.ACTIVE, is_active=True,
        ).select_related("rule"):
            active_by_student.setdefault(req.student_id, []).append(req)

    # 3. Bulk-create the missing assignments.
    components = fee_structure.components or []
    base_paise = sum(int(c.get("amount_paise", 0)) for c in components)
    new_assignments = []
    for sid in missing_ids:
        active = active_by_student.get(sid, [])
        discount_lines = [
            discount_line_for_request(req, base_paise=base_paise)
            for req in active
            if discount_line_for_request(req, base_paise=base_paise)["amount_paise"] > 0
        ]
        new_assignments.append(StudentFeeAssignment(
            student=student_by_id[sid], fee_structure=fee_structure,
            structure_snapshot=fee_structure.components or [], discount_lines=discount_lines,
            created_by=user, updated_by=user,
        ))
    if new_assignments:
        StudentFeeAssignment.objects.bulk_create(new_assignments)
        for a in new_assignments:
            assignment_by_student[a.student_id] = a

    # 3b. Refresh discount_lines on existing assignments only when students have active concessions.
    students_with_concessions = set(
        StudentConcession.objects.filter(
            student_id__in=student_ids,
            status=StudentConcessionStatus.ACTIVE,
            is_active=True,
        ).values_list("student_id", flat=True)
    )
    if students_with_concessions:
        from apps.fees.services.concession_sync import rebuild_assignment_discounts
        for assignment in assignment_by_student.values():
            if assignment.student_id in students_with_concessions:
                rebuild_assignment_discounts(assignment, user=user)

    # 4. Which assignments already have an invoice, in one query.
    assignment_ids = [a.id for a in assignment_by_student.values()]
    already_invoiced = set(
        FeeInvoice.objects.filter(assignment_id__in=assignment_ids, is_active=True)
        .values_list("assignment_id", flat=True)
    )

    guardian_by_user_id = _billing_guardian_map(students)

    invoices_to_create: list[FeeInvoice] = []
    lines_to_create: list[FeeInvoiceLine] = []
    installments_to_create: list[Installment] = []

    for student in students:
        assignment = assignment_by_student.get(student.id)
        if assignment is None or assignment.id in already_invoiced:
            continue

        components = assignment.structure_snapshot or []
        discount_lines = assignment.discount_lines or []
        total_components_paise = sum(int(c.get("amount_paise", 0)) for c in components)
        total_discount_paise = sum(int(d.get("amount_paise", 0)) for d in discount_lines)
        total_invoice_paise = max(total_components_paise - total_discount_paise, 0)

        billing_guardian = guardian_by_user_id.get(student.user_id)

        due_dates = [
            datetime.date.fromisoformat(c["due_date"]) for c in components if c.get("due_date")
        ]
        due_date = max(due_dates) if due_dates else datetime.date.today()

        invoice = FeeInvoice(
            branch=branch, student=student, assignment=assignment,
            billing_guardian=billing_guardian, due_date=due_date,
            total_paise=total_invoice_paise, paid_paise=0,
            status=InvoiceStatus.PAID if total_invoice_paise == 0 else InvoiceStatus.DUE,
            created_by=user, updated_by=user,
        )
        invoices_to_create.append(invoice)

        for c in components:
            lines_to_create.append(FeeInvoiceLine(
                invoice=invoice, kind=c.get("kind", "other"), label=c.get("label", "Fee Component"),
                amount_paise=int(c.get("amount_paise", 0)),
                created_by=user, updated_by=user,
            ))

        installment_groups: dict = {}
        for c in components:
            inst_no = int(c.get("installment_no", 1))
            installment_groups.setdefault(inst_no, []).append(c)

        installment_totals = {}
        installment_due_dates = {}
        for inst_no, inst_components in installment_groups.items():
            installment_totals[inst_no] = sum(int(c.get("amount_paise", 0)) for c in inst_components)
            inst_due_dates = [
                datetime.date.fromisoformat(c.get("due_date"))
                for c in inst_components if c.get("due_date")
            ]
            installment_due_dates[inst_no] = max(inst_due_dates) if inst_due_dates else due_date

        # Distribute discount across installments proportionally.
        remaining_discount = total_discount_paise
        inst_nos = sorted(installment_totals.keys())
        for idx, inst_no in enumerate(inst_nos):
            inst_components_total = installment_totals[inst_no]
            if total_components_paise > 0:
                if idx == len(inst_nos) - 1:
                    inst_discount = remaining_discount  # last one gets the remainder
                else:
                    inst_discount = (total_discount_paise * inst_components_total) // total_components_paise
                    remaining_discount -= inst_discount
            else:
                inst_discount = 0

            inst_amount = max(inst_components_total - inst_discount, 0)
            installments_to_create.append(Installment(
                invoice=invoice, sequence=inst_no, amount_paise=inst_amount, paid_paise=0,
                due_date=installment_due_dates[inst_no],
                status=InvoiceStatus.PAID if inst_amount == 0 else InvoiceStatus.DUE,
                created_by=user, updated_by=user,
            ))

    if invoices_to_create:
        FeeInvoice.objects.bulk_create(invoices_to_create)
    if lines_to_create:
        FeeInvoiceLine.objects.bulk_create(lines_to_create)
    if installments_to_create:
        Installment.objects.bulk_create(installments_to_create)

    return invoices_to_create
