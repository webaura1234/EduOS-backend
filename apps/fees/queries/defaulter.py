"""Queries — Defaulter / past due invoices."""

from django.db.models import F, Q
from django.utils import timezone

from apps.fees.enums import InvoiceStatus
from apps.fees.models import FeeInvoice, Installment


def list_defaulters(branch_id):
    """Unpaid invoices past due at invoice or installment level."""
    today = timezone.localdate()
    overdue_installment_invoice_ids = Installment.objects.filter(
        invoice__branch_id=branch_id,
        invoice__is_active=True,
        invoice__status__in=[InvoiceStatus.DUE, InvoiceStatus.PARTIAL],
        paid_paise__lt=F("amount_paise"),
        due_date__lt=today,
    ).values_list("invoice_id", flat=True)
    return FeeInvoice.objects.filter(
        branch_id=branch_id,
        status__in=[InvoiceStatus.DUE, InvoiceStatus.PARTIAL],
        is_active=True,
    ).filter(
        Q(pk__in=overdue_installment_invoice_ids) | Q(due_date__lt=today),
    ).select_related("student", "student__student_profile__user").order_by("due_date")
