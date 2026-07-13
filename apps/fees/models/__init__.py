"""
Fees models (school → parent tuition collection).

Structure → Assignment → Invoice → Payment → Receipt, plus Refund, Concession,
CreditNote, and the webhook idempotency log.
"""

from apps.fees.enums import (
    CarryForwardState,
    CreditNoteStatus,
    FeeComponentKind,
    FeeHeadBillingType,
    FeeHeadChargeType,
    FeeHeadRefundType,
    FeeStructureStatus,
    InvoiceStatus,
    OpeningBalanceSource,
    PaymentMethod,
    PaymentStatus,
    RefundStatus,
    StudentConcessionStatus,
)

from .concession import ConcessionRule, CreditNote, StudentConcession, WebhookEventLog
from .fee_head import FeeHead
from .invoice import FeeInvoice, FeeInvoiceLine, Installment
from .payment import Payment, Receipt, ReceiptCounter, Refund
from .structure import FeeStructure, StudentFeeAssignment

__all__ = [
    "FeeStructure",
    "StudentFeeAssignment",
    "FeeHead",
    "FeeInvoice",
    "FeeInvoiceLine",
    "Installment",
    "Payment",
    "Receipt",
    "ReceiptCounter",
    "Refund",
    "ConcessionRule",
    "StudentConcession",
    "ConcessionRequest",
    "CreditNote",
    "WebhookEventLog",
    # enums
    "FeeComponentKind",
    "FeeStructureStatus",
    "FeeHeadChargeType",
    "FeeHeadBillingType",
    "FeeHeadRefundType",
    "InvoiceStatus",
    "CarryForwardState",
    "OpeningBalanceSource",
    "PaymentStatus",
    "PaymentMethod",
    "RefundStatus",
    "StudentConcessionStatus",
    "ConcessionStatus",
    "CreditNoteStatus",
]

# Backward-compatible alias
ConcessionRequest = StudentConcession
ConcessionStatus = StudentConcessionStatus
