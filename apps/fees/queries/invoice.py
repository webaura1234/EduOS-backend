"""Queries — FeeInvoice, FeeInvoiceLine, and Installment."""

from django.db.models import F

from apps.fees.enums import CarryForwardState, InvoiceStatus
from apps.fees.models import FeeInvoice, FeeInvoiceLine, Installment

COLLECTIBLE_STATUSES = [InvoiceStatus.DUE, InvoiceStatus.PARTIAL]


def is_collectible_outstanding(invoice: FeeInvoice) -> bool:
    """True when an invoice still counts toward collectible outstanding balance."""
    return (
        invoice.is_active
        and invoice.carry_forward_state == CarryForwardState.NORMAL
        and invoice.status in COLLECTIBLE_STATUSES
        and invoice.balance_paise > 0
    )


def outstanding_invoices_qs(*, enrollment_id=None, branch_id=None):
    """Active invoices with a collectible balance (excludes carried-forward lifecycle)."""
    qs = FeeInvoice.objects.filter(
        is_active=True,
        carry_forward_state=CarryForwardState.NORMAL,
        status__in=COLLECTIBLE_STATUSES,
        total_paise__gt=F("paid_paise"),
    )
    if enrollment_id is not None:
        qs = qs.filter(student_id=enrollment_id)
    if branch_id is not None:
        qs = qs.filter(branch_id=branch_id)
    return qs


def outstanding_balance_paise(enrollment_id) -> int:
    return sum(inv.balance_paise for inv in outstanding_invoices_qs(enrollment_id=enrollment_id))


def mark_invoices_carried_forward(source_enrollment_id, opening_invoice, user=None) -> int:
    """Mark source invoices as carried forward; preserve status and amounts."""
    update_kwargs = {
        "carry_forward_state": CarryForwardState.CARRIED_FORWARD,
        "carried_forward_to": opening_invoice,
    }
    if user is not None:
        update_kwargs["updated_by"] = user
    return outstanding_invoices_qs(enrollment_id=source_enrollment_id).update(**update_kwargs)


def get_invoice_by_id(invoice_id) -> FeeInvoice | None:
    try:
        return FeeInvoice.objects.get(pk=invoice_id, is_active=True)
    except (FeeInvoice.DoesNotExist, ValueError, TypeError):
        return None


def get_invoice_for_update(invoice_id) -> FeeInvoice | None:
    return FeeInvoice.objects.select_for_update().filter(pk=invoice_id, is_active=True).first()


def invoice_exists_for_assignment(assignment_id) -> bool:
    return FeeInvoice.objects.filter(assignment_id=assignment_id, is_active=True).exists()


def list_branch_ledger(branch_id):
    """Open-due invoices for a branch (balance > 0) — super-admin branch fee ledger."""
    return (
        outstanding_invoices_qs(branch_id=branch_id)
        .select_related("student__student_profile__user", "branch")
        .order_by("-updated_at")
    )


def list_dues_for_student(student_id):
    return FeeInvoice.objects.filter(student_id=student_id, is_active=True).order_by("due_date")


def list_dues_for_student_user(student_user_id):
    from django.db.models import F, Q

    return (
        FeeInvoice.objects.filter(
            student__student_profile__user_id=student_user_id,
            is_active=True,
        )
        .filter(Q(student__is_active=True) | Q(total_paise__gt=F("paid_paise")))
        .prefetch_related("installments", "lines")
        .order_by("due_date")
    )


def get_invoice_for_student_user(invoice_id, student_user_id) -> FeeInvoice | None:
    try:
        return FeeInvoice.objects.get(pk=invoice_id, student__student_profile__user_id=student_user_id, is_active=True)
    except (FeeInvoice.DoesNotExist, ValueError, TypeError):
        return None


def _recompute_status(invoice: FeeInvoice):
    if invoice.paid_paise >= invoice.total_paise:
        invoice.status = InvoiceStatus.PAID
    elif invoice.paid_paise > 0:
        invoice.status = InvoiceStatus.PARTIAL
    else:
        invoice.status = InvoiceStatus.DUE


def apply_amount_to_invoice(invoice: FeeInvoice, amount_paise: int, user=None) -> FeeInvoice:
    """Add a captured amount, distribute across installments, recompute status."""
    invoice.paid_paise += amount_paise
    _recompute_status(invoice)
    if user:
        invoice.updated_by = user
    invoice.save(update_fields=["paid_paise", "status", "updated_by", "updated_at"])

    remaining = amount_paise
    for inst in invoice.installments.all().order_by("sequence"):
        if remaining <= 0:
            break
        if inst.status == InvoiceStatus.PAID:
            continue
        needed = inst.amount_paise - inst.paid_paise
        if needed <= 0:
            continue
        allocated = min(remaining, needed)
        inst.paid_paise += allocated
        inst.status = InvoiceStatus.PAID if inst.paid_paise >= inst.amount_paise else InvoiceStatus.PARTIAL
        inst.save(update_fields=["paid_paise", "status", "updated_at"])
        remaining -= allocated
    return invoice


def get_invoice_for_student(invoice_id, student_id) -> FeeInvoice | None:
    try:
        return FeeInvoice.objects.get(pk=invoice_id, student_id=student_id, is_active=True)
    except (FeeInvoice.DoesNotExist, ValueError, TypeError):
        return None


def reverse_amount_from_invoice(invoice: FeeInvoice, amount_paise: int, user=None) -> FeeInvoice:
    """Reduce paid amount across installments (newest first) after a refund."""
    invoice.paid_paise = max(invoice.paid_paise - amount_paise, 0)
    _recompute_status(invoice)
    if user:
        invoice.updated_by = user
    invoice.save(update_fields=["paid_paise", "status", "updated_by", "updated_at"])

    remaining = amount_paise
    for inst in invoice.installments.all().order_by("-sequence"):
        if remaining <= 0:
            break
        if inst.paid_paise <= 0:
            continue
        reduced = min(remaining, inst.paid_paise)
        inst.paid_paise -= reduced
        inst.status = (
            InvoiceStatus.DUE if inst.paid_paise == 0
            else InvoiceStatus.PARTIAL if inst.paid_paise < inst.amount_paise
            else InvoiceStatus.PAID
        )
        inst.save(update_fields=["paid_paise", "status", "updated_at"])
        remaining -= reduced
    return invoice


def adjust_invoice_total(invoice: FeeInvoice, delta_paise: int, user=None) -> FeeInvoice:
    """Increase/decrease the total (e.g. approved credit note); recompute status."""
    invoice.total_paise = max(invoice.total_paise + delta_paise, 0)
    _recompute_status(invoice)
    if user:
        invoice.updated_by = user
    invoice.save(update_fields=["total_paise", "status", "updated_by", "updated_at"])
    return invoice


def _recompute_installment_status(inst: Installment):
    if inst.paid_paise >= inst.amount_paise:
        inst.status = InvoiceStatus.PAID
    elif inst.paid_paise > 0:
        inst.status = InvoiceStatus.PARTIAL
    else:
        inst.status = InvoiceStatus.DUE


def reduce_installment_totals(invoice: FeeInvoice, amount_paise: int, user=None) -> None:
    """Lower installment billed amounts (newest first) after a credit or concession."""
    remaining = amount_paise
    for inst in invoice.installments.all().order_by("-sequence"):
        if remaining <= 0:
            break
        reducible = max(0, inst.amount_paise - inst.paid_paise)
        if reducible <= 0:
            continue
        cut = min(remaining, reducible)
        inst.amount_paise -= cut
        _recompute_installment_status(inst)
        if user:
            inst.updated_by = user
        inst.save(update_fields=["amount_paise", "status", "updated_by", "updated_at"])
        remaining -= cut


def sync_open_invoice_with_assignment(assignment, user=None) -> None:
    """Recalculate an open invoice when assignment discounts change after generation."""
    try:
        invoice = FeeInvoice.objects.select_for_update().prefetch_related("installments").get(
            assignment_id=assignment.id,
            is_active=True,
            status__in=[InvoiceStatus.DUE, InvoiceStatus.PARTIAL],
        )
    except FeeInvoice.DoesNotExist:
        return

    components = assignment.structure_snapshot or []
    discount_lines = assignment.discount_lines or []
    total_components_paise = sum(int(c.get("amount_paise", 0)) for c in components)
    total_discount_paise = sum(int(d.get("amount_paise", 0)) for d in discount_lines)
    new_total_paise = max(total_components_paise - total_discount_paise, 0)
    delta = new_total_paise - invoice.total_paise
    if delta == 0:
        return
    adjust_invoice_total(invoice, delta, user=user)
    if delta < 0:
        reduce_installment_totals(invoice, -delta, user=user)


def write_off_invoice(invoice: FeeInvoice, user=None) -> FeeInvoice:
    """Mark invoice and open installments as written off."""
    invoice.status = InvoiceStatus.WRITTEN_OFF
    invoice.paid_paise = invoice.total_paise
    if user:
        invoice.updated_by = user
    invoice.save(update_fields=["status", "paid_paise", "updated_by", "updated_at"])
    for inst in invoice.installments.exclude(status=InvoiceStatus.PAID):
        inst.status = InvoiceStatus.WRITTEN_OFF
        inst.paid_paise = inst.amount_paise
        inst.save(update_fields=["status", "paid_paise", "updated_at"])
    return invoice


def list_invoices(branch_id, student_id=None, status=None):
    qs = FeeInvoice.objects.filter(branch_id=branch_id, is_active=True).select_related(
        "student", "student__student_profile__user", "student__batch", "student__batch__course",
        "assignment", "billing_guardian",
    )
    if student_id:
        qs = qs.filter(student_id=student_id)
    if status:
        qs = qs.filter(status=status)
    return qs.order_by("-created_at")


def get_invoice(branch_id, invoice_id) -> FeeInvoice | None:
    try:
        return FeeInvoice.objects.prefetch_related("lines", "installments").get(
            branch_id=branch_id, pk=invoice_id, is_active=True
        )
    except (FeeInvoice.DoesNotExist, ValueError, TypeError):
        return None


def create_invoice(
    *,
    branch,
    student,
    assignment=None,
    billing_guardian=None,
    due_date=None,
    total_paise=0,
    status="due",
    carry_forward_state=CarryForwardState.NORMAL,
    opening_balance_source_year=None,
    opening_balance_source=None,
    promotion_session=None,
    user=None,
) -> FeeInvoice:
    return FeeInvoice.objects.create(
        branch=branch,
        student=student,
        assignment=assignment,
        billing_guardian=billing_guardian,
        due_date=due_date,
        total_paise=total_paise,
        paid_paise=0,
        status=status,
        carry_forward_state=carry_forward_state,
        opening_balance_source_year=opening_balance_source_year,
        opening_balance_source=opening_balance_source,
        promotion_session=promotion_session,
        created_by=user,
        updated_by=user,
    )


def create_invoice_line(*, invoice, kind, label, amount_paise, user=None) -> FeeInvoiceLine:
    return FeeInvoiceLine.objects.create(
        invoice=invoice,
        kind=kind,
        label=label,
        amount_paise=amount_paise,
        created_by=user,
        updated_by=user,
    )


def create_installment(*, invoice, sequence, amount_paise, due_date=None, status="due", user=None) -> Installment:
    return Installment.objects.create(
        invoice=invoice,
        sequence=sequence,
        amount_paise=amount_paise,
        paid_paise=0,
        due_date=due_date,
        status=status,
        created_by=user,
        updated_by=user,
    )
