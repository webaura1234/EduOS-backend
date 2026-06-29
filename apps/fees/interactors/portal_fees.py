"""Composed student/parent portal fees payload."""

import datetime

from django.conf import settings as dj_settings
from django.db.models import F, Q

from apps.examinations.models import ExamRegistration
from apps.fees.enums import FeeComponentKind, InvoiceStatus, PaymentStatus
from apps.fees.models import FeeInvoice
from apps.fees.queries.invoice import list_dues_for_student_user
from apps.fees.queries.portal import list_receipts_for_student


def list_open_invoices_for_student_user(student_user_id):
    """Tuition invoices with balance; includes archived-enrollment dues (EC-XFER-03)."""
    return (
        FeeInvoice.objects.filter(
            student__student_profile__user_id=student_user_id,
            is_active=True,
        )
        .filter(Q(student__is_active=True) | Q(total_paise__gt=F("paid_paise")))
        .exclude(assignment__isnull=True)
        .prefetch_related("installments", "lines")
        .order_by("due_date")
    )


def _build_installment_schedule(invoices) -> list[dict]:
    rows = []
    today = datetime.date.today()
    for inv in invoices:
        for inst in inv.installments.all():
            amount = round(inst.amount_paise / 100, 2)
            paid = round(inst.paid_paise / 100, 2)
            balance = max(0.0, amount - paid)
            status = inst.status
            if status != InvoiceStatus.PAID and inst.due_date and inst.due_date < today:
                status = "overdue"
            rows.append({
                "invoiceId": str(inv.id),
                "installmentId": str(inst.id),
                "sequence": inst.sequence,
                "label": f"Installment {inst.sequence}",
                "dueDate": inst.due_date.isoformat() if inst.due_date else "",
                "amount": amount,
                "paid": paid,
                "balance": balance,
                "status": status,
            })
    return sorted(rows, key=lambda r: (r["dueDate"], r["sequence"]))


def _build_exam_fees(student_user_id) -> dict:
    regs = (
        ExamRegistration.objects.filter(
            student__student_profile__user_id=student_user_id,
            is_active=True,
        )
        .select_related("exam", "fee_invoice")
        .order_by("exam__name")
    )
    rows = []
    for reg in regs:
        invoice = reg.fee_invoice
        if invoice is None:
            continue
        exam = reg.exam
        exam_line = invoice.lines.filter(kind=FeeComponentKind.EXAM).first()
        amount = round((exam_line.amount_paise if exam_line else invoice.total_paise) / 100, 2)
        if reg.fee_paid or invoice.status == InvoiceStatus.PAID:
            status = "paid"
            paid_at = ""
            if invoice.payments.filter(status=PaymentStatus.CAPTURED).exists():
                p = invoice.payments.filter(status=PaymentStatus.CAPTURED).order_by("-captured_at").first()
                paid_at = p.captured_at.isoformat() if p and p.captured_at else ""
        elif invoice.status == InvoiceStatus.WRITTEN_OFF:
            status = "cancelled"
            paid_at = None
        else:
            status = "unpaid"
            paid_at = None
        rows.append({
            "examSlotId": str(exam.pk),
            "examLabel": exam.name,
            "examDate": exam.academic_period.end_date.isoformat() if exam.academic_period_id else "",
            "amount": amount,
            "invoiceId": str(invoice.id),
            "status": status,
            "paidAt": paid_at,
        })
    all_paid = len(rows) == 0 or all(r["status"] == "paid" for r in rows)
    return {"rows": rows, "allPaid": all_paid}


def build_portal_fees_payload(*, student_user_id, tenant) -> dict:
    inst = "college" if getattr(tenant, "institution_type", "") == "college" else "school"
    tuition_invoices = list(list_open_invoices_for_student_user(student_user_id))
    exam_invoice_ids = set(
        FeeInvoice.objects.filter(
            student__student_profile__user_id=student_user_id,
            assignment__isnull=True,
            is_active=True,
            lines__kind=FeeComponentKind.EXAM,
        ).values_list("pk", flat=True)
    )
    invoices = [i for i in list(list_dues_for_student_user(student_user_id)) if i.pk not in exam_invoice_ids]

    total_due = sum(i.total_paise for i in invoices)
    paid = sum(i.paid_paise for i in invoices)
    balance = sum(i.balance_paise for i in invoices)
    today = datetime.date.today()
    open_due_dates = [i.due_date for i in invoices if i.due_date and i.balance_paise > 0]
    next_due = min(open_due_dates).isoformat() if open_due_dates else None
    is_overdue = any(d < today for d in open_due_dates)

    payments = []
    for r in list_receipts_for_student(student_user_id):
        p = r.payment
        payments.append({
            "id": str(r.id),
            "paidAt": r.issued_at.isoformat() if r.issued_at else "",
            "amount": round(p.amount_paise / 100, 2),
            "method": p.method,
            "receiptNo": f"{r.financial_year}/{r.sequence_number}",
            "orderId": p.razorpay_order_id or "",
            "status": p.status,
        })

    next_installment = None
    schedule = _build_installment_schedule(tuition_invoices)
    for row in schedule:
        if row["balance"] > 0:
            next_installment = row
            break

    return {
        "institutionType": inst,
        "ledger": {
            "totalDue": round(total_due / 100, 2),
            "paid": round(paid / 100, 2),
            "balance": round(balance / 100, 2),
            "nextDueDate": next_installment["dueDate"] if next_installment else next_due,
            "isOverdue": is_overdue or any(r["status"] == "overdue" for r in schedule),
        },
        "payments": payments,
        "razorpayKeyId": dj_settings.RAZORPAY_KEY_ID,
        "examFees": _build_exam_fees(student_user_id),
        "installmentSchedule": schedule,
    }
