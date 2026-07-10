"""Central concession sync — rebuild discount_lines and sync open invoices."""

from django.core.exceptions import ValidationError

from apps.fees.enums import InvoiceStatus, StudentConcessionStatus
from apps.fees.helpers.concession import discount_line_for_request
from apps.fees.queries.concession import (
    has_active_concession_for_profile,
    list_active_concessions_for_profile,
    list_active_concessions_for_student,
    update_student_concession,
)
from apps.fees.queries.invoice import sync_open_invoice_with_assignment
from apps.fees.queries.structure import update_assignment


def assert_concession_modifiable(student_id) -> None:
    """Block apply/edit when all assignment-linked invoices are fully paid."""
    from apps.fees.models import FeeInvoice

    has_assignment_invoice = FeeInvoice.objects.filter(
        student_id=student_id, is_active=True, assignment__isnull=False,
    ).exists()
    if not has_assignment_invoice:
        return
    has_open = FeeInvoice.objects.filter(
        student_id=student_id,
        is_active=True,
        assignment__isnull=False,
        status__in=[InvoiceStatus.DUE, InvoiceStatus.PARTIAL],
    ).exists()
    if not has_open:
        raise ValidationError(
            "Invoice is fully paid. Use Scholarships / credit note or refund process."
        )


def rebuild_assignment_discounts(assignment, *, user=None):
    """Rebuild discount_lines from all active concessions for the student profile."""
    profile_id = assignment.student.student_profile_id
    branch_id = assignment.student.branch_id
    active = list_active_concessions_for_profile(branch_id=branch_id, profile_id=profile_id)
    components = assignment.structure_snapshot or []
    base_paise = sum(int(c.get("amount_paise", 0)) for c in components)
    lines = []
    seen_concession_ids: set[str] = set()
    seen_rule_ids: set[str] = set()
    for conc in active:
        cid = str(conc.id)
        rule_key = str(conc.rule_id) if conc.rule_id else cid
        if cid in seen_concession_ids or rule_key in seen_rule_ids:
            continue
        line = discount_line_for_request(conc, base_paise=base_paise)
        if line["amount_paise"] > 0:
            lines.append(line)
            seen_concession_ids.add(cid)
            seen_rule_ids.add(rule_key)
            if conc.amount_paise != line["amount_paise"]:
                update_student_concession(conc, {"amount_paise": line["amount_paise"]}, user=user)
    update_assignment(assignment, {"discount_lines": lines}, user=user)
    sync_open_invoice_with_assignment(assignment, user=user)
    return assignment


def sync_student_concessions(student_id, *, user=None) -> None:
    """Refresh all assignments for the student profile after concession apply/revoke/edit."""
    from apps.admissions.models import StudentEnrollment
    from apps.fees.models import StudentFeeAssignment

    enrollment = StudentEnrollment.objects.filter(pk=student_id, is_active=True).first()
    if not enrollment:
        return
    assignments = StudentFeeAssignment.objects.filter(
        student__student_profile_id=enrollment.student_profile_id,
        student__branch_id=enrollment.branch_id,
        is_active=True,
    ).select_related("student")
    for assignment in assignments:
        rebuild_assignment_discounts(assignment, user=user)
