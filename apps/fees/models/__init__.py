"""
Fees models (school → parent tuition collection).

Structure → Assignment → Invoice → Payment → Receipt, plus Refund, Concession,
CreditNote, and the webhook idempotency log.
"""

from apps.fees.enums import (
    ConcessionStatus,
    CreditNoteStatus,
    FeeComponentKind,
    InvoiceStatus,
    PaymentMethod,
    PaymentStatus,
    RefundStatus,
)

from .concession import ConcessionRequest, ConcessionRule, CreditNote, WebhookEventLog
from .invoice import FeeInvoice, FeeInvoiceLine, Installment
from .payment import Payment, Receipt, ReceiptCounter, Refund
from .structure import FeeStructure, StudentFeeAssignment

__all__ = [
    "FeeStructure",
    "StudentFeeAssignment",
    "FeeInvoice",
    "FeeInvoiceLine",
    "Installment",
    "Payment",
    "Receipt",
    "ReceiptCounter",
    "Refund",
    "ConcessionRule",
    "ConcessionRequest",
    "CreditNote",
    "WebhookEventLog",
    # enums
    "FeeComponentKind",
    "InvoiceStatus",
    "PaymentStatus",
    "PaymentMethod",
    "RefundStatus",
    "ConcessionStatus",
    "CreditNoteStatus",
]
