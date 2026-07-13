"""Fee export definitions — registered on app startup via FeesConfig.ready()."""

from apps.accounts.models.user import Role
from apps.analytics.enums import ReportType
from apps.core.exports.base import AggregationExportDefinition, Column, ExportDefinition, FilterSpec
from apps.core.exports.registry import register


class FeeLedgerExport(ExportDefinition):
    """All fee invoices for a branch, optionally filtered by date range."""

    report_type = ReportType.FEE_LEDGER
    title = "Fee Ledger"
    module = "fees"
    description = "All fee invoices with gross, concession, paid, and balance"
    allowed_roles = [Role.ADMIN, Role.SUPER_ADMIN]
    formats = ["csv"]
    sync_threshold = 100
    supports_preview = True
    supports_search = True
    estimated_runtime = "background"
    filters = [
        FilterSpec("fromDate", "From Date", type="date"),
        FilterSpec("toDate", "To Date", type="date"),
        FilterSpec("status", "Status", type="text"),
    ]

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
            "student__student_profile__user", "student__batch", "student__batch__course", "branch", "assignment__fee_structure"
        ).order_by("created_at")

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("invoice_number", "Invoice Number"),
            Column("admission_no", "Admission No"),
            Column("student_name", "Student Name"),
            Column("class_name", "Class"),
            Column("section_name", "Section"),
            Column("structure_name", "Fee Structure"),
            Column("gross_amount", "Gross Fee (₹)", format="number"),
            Column("concession", "Concession (₹)", format="number"),
            Column("amount", "Net Fee (₹)", format="number"),
            Column("paid", "Paid (₹)", format="number"),
            Column("balance", "Outstanding (₹)", format="number"),
            Column("due_date", "Due Date", format="date"),
            Column("status", "Status"),
            Column("branch", "Branch"),
            Column("generated_date", "Generated Date", format="date"),
        ]

    def get_row(self, invoice) -> dict:
        student_name = ""
        admission_no = ""
        class_name = ""
        section_name = ""
        try:
            student_name = invoice.student.user.full_name
            admission_no = invoice.student.student_profile.admission_number
            if invoice.student.batch_id:
                section_name = invoice.student.batch.name
                class_name = invoice.student.batch.course.name if invoice.student.batch.course_id else ""
        except Exception:  # noqa: BLE001
            pass
        structure_name = ""
        try:
            if invoice.assignment_id and invoice.assignment.fee_structure_id:
                fs = invoice.assignment.fee_structure
                structure_name = fs.name
        except Exception:  # noqa: BLE001
            pass
        gross_paise = 0
        concession_paise = 0
        try:
            if invoice.assignment_id:
                components = invoice.assignment.structure_snapshot or []
                gross_paise = sum(int(c.get("amount_paise", 0)) for c in components)
                concession_paise = sum(
                    int(d.get("amount_paise", 0)) for d in (invoice.assignment.discount_lines or [])
                )
        except Exception:  # noqa: BLE001
            pass
        if gross_paise == 0:
            gross_paise = invoice.total_paise + concession_paise

        from django.utils import timezone

        balance_paise = invoice.balance_paise
        if invoice.carry_forward_state == "carried_forward":
            balance_paise = 0
        
        # Use existing 'invoice_number' if it exists on the model, otherwise truncate ID
        invoice_num = getattr(invoice, 'invoice_number', getattr(invoice, 'number', str(invoice.pk)[:8].upper()))
        
        return {
            "invoice_number": invoice_num,
            "admission_no": admission_no,
            "student_name": student_name,
            "class_name": class_name,
            "section_name": section_name,
            "structure_name": structure_name,
            "gross_amount": round(gross_paise / 100, 2),
            "concession": round(concession_paise / 100, 2),
            "amount": round(invoice.total_paise / 100, 2),
            "paid": round(invoice.paid_paise / 100, 2),
            "balance": round(balance_paise / 100, 2),
            "due_date": invoice.due_date.isoformat() if invoice.due_date else "",
            "status": invoice.get_status_display(),
            "branch": invoice.branch.name,
            "generated_date": timezone.now().date().isoformat(),
        }

    def get_filename(self, params: dict) -> str:
        suffix = params.get("fromDate", "all")
        return f"fee-ledger-{suffix}"


class FeeDefaultersExport(ExportDefinition):
    """Unpaid (due/partial) invoices past their due date for a branch."""

    report_type = ReportType.FEE_DEFAULTERS
    title = "Fee Defaulters"
    module = "fees"
    description = "Students with overdue balances"
    allowed_roles = [Role.ADMIN, Role.SUPER_ADMIN]
    formats = ["csv"]
    sync_threshold = 500
    supports_preview = True
    estimated_runtime = "instant"

    def get_queryset(self, *, tenant_id, branch_id, params: dict):
        from django.utils import timezone
        from apps.fees.enums import CarryForwardState, InvoiceStatus
        from apps.fees.models import FeeInvoice

        today = timezone.localdate()
        qs = FeeInvoice.objects.filter(
            branch__tenant_id=tenant_id,
            status__in=[InvoiceStatus.DUE, InvoiceStatus.PARTIAL],
            carry_forward_state=CarryForwardState.NORMAL,
            due_date__lt=today,
            is_active=True,
        )
        if branch_id:
            qs = qs.filter(branch_id=branch_id)
        return qs.select_related(
            "student__student_profile__user", "student__batch", "student__batch__course", "branch", "assignment__fee_structure"
        ).prefetch_related(
            "student__student_profile__user__guardian_links__guardian"
        ).order_by("due_date")

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("admission_no", "Admission No"),
            Column("student_name", "Student Name"),
            Column("parent_name", "Parent Name"),
            Column("phone_number", "Phone Number"),
            Column("class_name", "Class"),
            Column("section_name", "Section"),
            Column("balance", "Outstanding Amount (₹)", format="number"),
            Column("last_payment", "Last Payment"),
            Column("due_date", "Due Date", format="date"),
            Column("days_overdue", "Days Overdue", format="number"),
            Column("priority", "Priority"),
            Column("status", "Status"),
        ]

    def get_row(self, invoice) -> dict:
        student_name = ""
        admission_no = ""
        class_name = ""
        section_name = ""
        parent_name = ""
        phone_number = ""
        
        try:
            student_user = invoice.student.student_profile.user
            student_name = student_user.full_name
            admission_no = invoice.student.student_profile.admission_number
            if invoice.student.batch_id:
                section_name = invoice.student.batch.name
                class_name = invoice.student.batch.course.name if invoice.student.batch.course_id else ""
            
            # Guardian info
            phone_number = invoice.student.student_profile.guardian_phone or ""
            guardian_links = list(student_user.guardian_links.all())
            if guardian_links:
                primary = next((gl for gl in guardian_links if gl.is_primary_contact), guardian_links[0])
                parent_name = primary.guardian.full_name
        except Exception:  # noqa: BLE001
            pass
            
        from django.utils import timezone
        today = timezone.localdate()
        days_overdue = (today - invoice.due_date).days if invoice.due_date else 0
        
        priority = "Low"
        if days_overdue > 30:
            priority = "High"
        elif days_overdue > 14:
            priority = "Medium"
            
        return {
            "admission_no": admission_no,
            "student_name": student_name,
            "parent_name": parent_name,
            "phone_number": phone_number,
            "class_name": class_name,
            "section_name": section_name,
            "balance": round(invoice.balance_paise / 100, 2),
            "last_payment": "-",  # Simplified; would require payment logs prefetch
            "due_date": invoice.due_date.isoformat() if invoice.due_date else "",
            "days_overdue": max(0, days_overdue),
            "priority": priority,
            "status": invoice.get_status_display(),
        }

    def get_filename(self, params: dict) -> str:
        return "fee-defaulters"


class StudentFeeStatementExport(ExportDefinition):
    """A student's own fee invoices + payment history — all branches, all years."""

    report_type = ReportType.STUDENT_FEE_STATEMENT
    title = "My Fee Statement"
    module = "fees"
    description = "Your fee invoices across all branches"
    allowed_roles = [Role.STUDENT]
    formats = ["csv"]
    sync_threshold = 500
    catalog_visible = True
    estimated_runtime = "instant"

    def get_queryset(self, *, tenant_id, branch_id, params: dict):
        from apps.fees.models import FeeInvoice

        student_user_id = params.get("studentUserId")
        qs = FeeInvoice.objects.filter(
            student__student_profile__user_id=student_user_id,
            branch__tenant_id=tenant_id,
            is_active=True,
        )
        return qs.select_related("branch", "assignment").order_by("-created_at")

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("invoice_id", "Invoice ID"),
            Column("branch", "Branch"),
            Column("gross_amount", "Gross Amount (₹)", format="number"),
            Column("concession", "Concession (₹)", format="number"),
            Column("amount", "Net Amount (₹)", format="number"),
            Column("paid", "Paid (₹)", format="number"),
            Column("balance", "Balance (₹)", format="number"),
            Column("status", "Status"),
            Column("due_date", "Due Date", format="date"),
            Column("created_at", "Created At", format="date"),
        ]

    def get_row(self, invoice) -> dict:
        gross_paise = 0
        concession_paise = 0
        try:
            if invoice.assignment_id:
                components = invoice.assignment.structure_snapshot or []
                gross_paise = sum(int(c.get("amount_paise", 0)) for c in components)
                concession_paise = sum(
                    int(d.get("amount_paise", 0)) for d in (invoice.assignment.discount_lines or [])
                )
        except Exception:  # noqa: BLE001
            pass
        if gross_paise == 0:
            gross_paise = invoice.total_paise + concession_paise
        return {
            "invoice_id": str(invoice.pk),
            "branch": invoice.branch.name,
            "gross_amount": round(gross_paise / 100, 2),
            "concession": round(concession_paise / 100, 2),
            "amount": round(invoice.total_paise / 100, 2),
            "paid": round(invoice.paid_paise / 100, 2),
            "balance": round(invoice.balance_paise / 100, 2),
            "status": invoice.get_status_display(),
            "due_date": invoice.due_date.isoformat() if invoice.due_date else "",
            "created_at": invoice.created_at.date().isoformat() if invoice.created_at else "",
        }

    def get_filename(self, params: dict) -> str:
        return "my-fee-statement"


class FeeCollectionExport(AggregationExportDefinition):
    """Collections and dues grouped by batch."""

    report_type = ReportType.FEE_COLLECTION
    title = "Fee Collection Summary"
    module = "fees"
    description = "Collections and dues by batch"
    allowed_roles = [Role.ADMIN, Role.SUPER_ADMIN]
    formats = ["csv"]
    sync_threshold = 500
    supports_preview = True
    estimated_runtime = "instant"

    def get_columns(self, params: dict) -> list[Column]:
        return [
            Column("branch", "Branch"),
            Column("batchName", "Class"),
            Column("totalInvoiced", "Expected Collection (₹)", format="number"),
            Column("totalCollected", "Collected (₹)", format="number"),
            Column("totalPending", "Outstanding (₹)", format="number"),
            Column("concessions", "Concessions (₹)"),
            Column("collectionPercent", "Collection %", format="number"),
        ]

    def resolve_rows(self, *, tenant, branch, params: dict) -> list[dict]:
        from apps.fees.queries import report as report_q
        rows = report_q.collection_by_batch(branch.pk)
        for r in rows:
            r["branch"] = branch.name
            r["concessions"] = "-"  # Requires complex aggregation across discount lines
            invoiced = r.get("totalInvoiced", 0)
            collected = r.get("totalCollected", 0)
            r["collectionPercent"] = round((collected / invoiced * 100), 2) if invoiced > 0 else 0
        return rows


def register_all() -> None:
    register(FeeLedgerExport())
    register(FeeDefaultersExport())
    register(StudentFeeStatementExport())
    register(FeeCollectionExport())


register_all()
