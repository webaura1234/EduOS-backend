"""Fee export definitions — registered on app startup via FeesConfig.ready()."""

from apps.accounts.models.user import Role
from apps.analytics.enums import ReportType
from apps.core.exports.base import Column, ExportDefinition
from apps.core.exports.registry import register


class FeeLedgerExport(ExportDefinition):
    """All fee invoices for a branch, optionally filtered by date range."""

    report_type = ReportType.FEE_LEDGER
    title = "Fee Ledger"
    allowed_roles = [Role.ADMIN, Role.SUPER_ADMIN]
    formats = ["csv"]
    sync_threshold = 100

    def get_queryset(self, *, tenant_id, branch_id, params: dict):
        from apps.fees.models import FeeInvoice
        qs = FeeInvoice.objects.filter(branch__tenant_id=tenant_id, is_active=True)
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        if params.get("fromDate"):
            qs = qs.filter(created_at__date__gte=params["fromDate"])
        if params.get("toDate"):
            qs = qs.filter(created_at__date__lte=params["toDate"])
        if params.get("status"):
            qs = qs.filter(status=params["status"])
        return qs.select_related(
            "student__student_profile__user", "branch"
        ).order_by("created_at")

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("invoice_id", "Invoice ID"),
            Column("student_name", "Student Name"),
            Column("branch", "Branch"),
            Column("amount", "Total Amount (₹)", format="number"),
            Column("paid", "Paid (₹)", format="number"),
            Column("balance", "Balance (₹)", format="number"),
            Column("status", "Status"),
            Column("due_date", "Due Date", format="date"),
            Column("created_at", "Created At", format="date"),
        ]

    def get_row(self, invoice) -> dict:
        student_name = ""
        try:
            student_name = invoice.student.user.full_name
        except Exception:  # noqa: BLE001
            pass
        return {
            "invoice_id": str(invoice.pk),
            "student_name": student_name,
            "branch": invoice.branch.name,
            "amount": round(invoice.total_paise / 100, 2),
            "paid": round(invoice.paid_paise / 100, 2),
            "balance": round(invoice.balance_paise / 100, 2),
            "status": invoice.get_status_display(),
            "due_date": invoice.due_date.isoformat() if invoice.due_date else "",
            "created_at": invoice.created_at.date().isoformat() if invoice.created_at else "",
        }

    def get_filename(self, params: dict) -> str:
        suffix = params.get("fromDate", "all")
        return f"fee-ledger-{suffix}"


class FeeDefaultersExport(ExportDefinition):
    """Unpaid (due/partial) invoices past their due date for a branch."""

    report_type = ReportType.FEE_DEFAULTERS
    title = "Fee Defaulters"
    allowed_roles = [Role.ADMIN, Role.SUPER_ADMIN]
    formats = ["csv"]
    sync_threshold = 500

    def get_queryset(self, *, tenant_id, branch_id, params: dict):
        from django.utils import timezone
        from apps.fees.enums import InvoiceStatus
        from apps.fees.models import FeeInvoice

        today = timezone.localdate()
        qs = FeeInvoice.objects.filter(
            branch__tenant_id=tenant_id,
            status__in=[InvoiceStatus.DUE, InvoiceStatus.PARTIAL],
            due_date__lt=today,
            is_active=True,
        )
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        return qs.select_related(
            "student", "student__student_profile__user", "branch"
        ).order_by("due_date")

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("invoice_id", "Invoice ID"),
            Column("student_name", "Student Name"),
            Column("branch", "Branch"),
            Column("due_date", "Due Date", format="date"),
            Column("balance", "Balance (₹)", format="number"),
        ]

    def get_row(self, invoice) -> dict:
        student_name = ""
        try:
            student_name = invoice.student.user.full_name
        except Exception:  # noqa: BLE001
            pass
        return {
            "invoice_id": str(invoice.pk),
            "student_name": student_name,
            "branch": invoice.branch.name,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else "",
            "balance": round(invoice.balance_paise / 100, 2),
        }

    def get_filename(self, params: dict) -> str:
        return "fee-defaulters"


class StudentFeeStatementExport(ExportDefinition):
    """A student's own fee invoices + payment history — all branches, all years."""

    report_type = ReportType.STUDENT_FEE_STATEMENT
    title = "My Fee Statement"
    allowed_roles = [Role.STUDENT]
    formats = ["csv"]
    sync_threshold = 500

    def get_queryset(self, *, tenant_id, branch_id, params: dict):
        from apps.fees.models import FeeInvoice

        student_user_id = params.get("studentUserId")
        qs = FeeInvoice.objects.filter(
            student__student_profile__user_id=student_user_id,
            branch__tenant_id=tenant_id,
            is_active=True,
        )
        return qs.select_related("branch").order_by("-created_at")

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("invoice_id", "Invoice ID"),
            Column("branch", "Branch"),
            Column("amount", "Total Amount (₹)", format="number"),
            Column("paid", "Paid (₹)", format="number"),
            Column("balance", "Balance (₹)", format="number"),
            Column("status", "Status"),
            Column("due_date", "Due Date", format="date"),
            Column("created_at", "Created At", format="date"),
        ]

    def get_row(self, invoice) -> dict:
        return {
            "invoice_id": str(invoice.pk),
            "branch": invoice.branch.name,
            "amount": round(invoice.total_paise / 100, 2),
            "paid": round(invoice.paid_paise / 100, 2),
            "balance": round(invoice.balance_paise / 100, 2),
            "status": invoice.get_status_display(),
            "due_date": invoice.due_date.isoformat() if invoice.due_date else "",
            "created_at": invoice.created_at.date().isoformat() if invoice.created_at else "",
        }

    def get_filename(self, params: dict) -> str:
        return "my-fee-statement"


def register_all() -> None:
    register(FeeLedgerExport())
    register(FeeDefaultersExport())
    register(StudentFeeStatementExport())


register_all()
