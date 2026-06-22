"""Queries — FeeInvoice, FeeInvoiceLine, and Installment."""

from apps.fees.enums import InvoiceStatus
from apps.fees.models import FeeInvoice, FeeInvoiceLine, Installment


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
    from django.db.models import F
    return (
        FeeInvoice.objects.filter(
            branch_id=branch_id, is_active=True, total_paise__gt=F("paid_paise")
        )
        .select_related("student__student_profile__user", "branch")
        .order_by("-updated_at")
    )


def list_dues_for_student(student_id):
    return FeeInvoice.objects.filter(student_id=student_id, is_active=True).order_by("due_date")


def list_dues_for_student_user(student_user_id):
    return FeeInvoice.objects.filter(student__student_profile__user_id=student_user_id, is_active=True).order_by("due_date")


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


def list_invoices(branch_id, student_id=None, status=None):
    qs = FeeInvoice.objects.filter(branch_id=branch_id, is_active=True).select_related(
        "student", "student__student_profile__user", "student__batch",
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


def create_invoice(*, branch, student, assignment=None, billing_guardian=None, due_date=None, total_paise=0, status="due", user=None) -> FeeInvoice:
    return FeeInvoice.objects.create(
        branch=branch,
        student=student,
        assignment=assignment,
        billing_guardian=billing_guardian,
        due_date=due_date,
        total_paise=total_paise,
        paid_paise=0,
        status=status,
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
