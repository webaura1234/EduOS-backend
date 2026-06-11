"""Queries — Defaulter / past due invoices."""

from django.utils import timezone

from apps.fees.enums import InvoiceStatus
from apps.fees.models import FeeInvoice


def list_defaulters(branch_id):
    """Returns a list of unpaid (due or partial) invoices that are past their due date."""
    today = timezone.localdate()
    return FeeInvoice.objects.filter(
        branch_id=branch_id,
        status__in=[InvoiceStatus.DUE, InvoiceStatus.PARTIAL],
        due_date__lt=today,
        is_active=True,
    ).select_related("student", "student__user").order_by("due_date")
