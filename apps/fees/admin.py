"""Django Admin configuration for fees models."""

from django.contrib import admin

from apps.fees.models import (
    ConcessionRequest,
    ConcessionRule,
    CreditNote,
    FeeInvoice,
    FeeInvoiceLine,
    FeeStructure,
    Installment,
    Payment,
    Receipt,
    ReceiptCounter,
    Refund,
    WebhookEventLog,
)


@admin.register(FeeStructure)
class FeeStructureAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "branch", "batch", "academic_year", "version", "created_at"]
    list_filter = ["branch", "academic_year"]
    search_fields = ["name"]


@admin.register(FeeInvoice)
class FeeInvoiceAdmin(admin.ModelAdmin):
    list_display = ["id", "student", "branch", "due_date", "total_paise", "paid_paise", "status", "created_at"]
    list_filter = ["branch", "status"]
    search_fields = ["student__student_profile__user__first_name", "student__student_profile__user__last_name", "id"]


@admin.register(FeeInvoiceLine)
class FeeInvoiceLineAdmin(admin.ModelAdmin):
    list_display = ["id", "invoice", "kind", "label", "amount_paise"]


@admin.register(Installment)
class InstallmentAdmin(admin.ModelAdmin):
    list_display = ["id", "invoice", "sequence", "amount_paise", "paid_paise", "status", "due_date"]


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = ["id", "invoice", "amount_paise", "method", "status", "razorpay_order_id", "razorpay_payment_id", "captured_at"]
    list_filter = ["method", "status"]
    search_fields = ["razorpay_order_id", "razorpay_payment_id", "idempotency_key"]


@admin.register(ReceiptCounter)
class ReceiptCounterAdmin(admin.ModelAdmin):
    list_display = ["id", "branch", "financial_year", "last_number"]


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ["id", "branch", "payment", "sequence_number", "financial_year", "issued_at"]
    list_filter = ["branch", "financial_year"]


@admin.register(Refund)
class RefundAdmin(admin.ModelAdmin):
    list_display = ["id", "payment", "amount_paise", "status", "razorpay_refund_id", "created_at"]
    list_filter = ["status"]


@admin.register(ConcessionRule)
class ConcessionRuleAdmin(admin.ModelAdmin):
    list_display = ["id", "name", "branch", "amount_paise", "percent"]


@admin.register(ConcessionRequest)
class ConcessionRequestAdmin(admin.ModelAdmin):
    list_display = ["id", "student", "rule", "amount_paise", "status", "requested_by", "approver", "decided_at"]
    list_filter = ["status"]


@admin.register(CreditNote)
class CreditNoteAdmin(admin.ModelAdmin):
    list_display = ["id", "student", "invoice", "amount_paise", "status", "approved_by", "decided_at"]
    list_filter = ["status"]


@admin.register(WebhookEventLog)
class WebhookEventLogAdmin(admin.ModelAdmin):
    list_display = ["event_id", "razorpay_payment_id", "processed_at"]
    search_fields = ["event_id", "razorpay_payment_id"]
