"""Composed student/parent portal fees payload."""

import datetime

from django.conf import settings as dj_settings
from django.db.models import F, Q

from apps.examinations.models import ExamRegistration
from apps.fees.enums import CarryForwardState, FeeComponentKind, InvoiceStatus, PaymentStatus
from apps.fees.models import FeeInvoice
from apps.fees.queries.invoice import is_collectible_outstanding
from apps.fees.queries.portal import list_receipts_for_student


def list_open_invoices_for_student_user(student_user_id):
    """Tuition invoices with balance; includes archived-enrollment dues (EC-XFER-03)."""
    return (
        FeeInvoice.objects.filter(
            student__student_profile__user_id=student_user_id,
            is_active=True,
            carry_forward_state=CarryForwardState.NORMAL,
        )
        .filter(Q(student__is_active=True) | Q(total_paise__gt=F("paid_paise")))
        .exclude(assignment__isnull=True)
        .prefetch_related("installments", "lines", "assignment")
        .order_by("due_date")
    )


def _installment_label(assignment, sequence: int) -> str:
    if not assignment:
        return f"Installment {sequence}"
    labels = []
    for c in assignment.structure_snapshot or []:
        if int(c.get("installment_no", 1)) == sequence:
            lbl = c.get("label") or c.get("name")
            if lbl:
                labels.append(str(lbl))
    return labels[0] if labels else f"Installment {sequence}"


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
                "label": _installment_label(inv.assignment, inst.sequence),
                "dueDate": inst.due_date.isoformat() if inst.due_date else "",
                "amount": amount,
                "paid": paid,
                "balance": balance,
                "status": status,
            })
    return sorted(rows, key=lambda r: (r["dueDate"], r["sequence"]))


def _concession_breakdown(invoices) -> dict:
    """Gross/concession from fee assignments once each — never re-sum the same structure."""
    gross_paise = 0
    concession_paise = 0
    lines: list[dict] = []
    seen_assignment_ids: set = set()

    for inv in invoices:
        assignment = getattr(inv, "assignment", None)
        if not assignment:
            gross_paise += int(inv.total_paise or 0)
            continue

        assignment_id = assignment.pk
        if assignment_id in seen_assignment_ids:
            # Extra invoice on the same assignment (e.g. opening-balance) — add face value only.
            gross_paise += int(inv.total_paise or 0)
            continue
        seen_assignment_ids.add(assignment_id)

        components = assignment.structure_snapshot or []
        snap_gross = sum(int(c.get("amount_paise", 0)) for c in components)
        discount_lines = assignment.discount_lines or []
        snap_concession = sum(
            int(d.get("amount_paise", 0)) for d in discount_lines if int(d.get("amount_paise", 0)) > 0
        )
        expected_net = max(snap_gross - snap_concession, 0)

        # Full tuition invoice matching the structure: show original + concessions.
        # Opening-balance / mismatched totals must not inflate Original fee from the full snapshot.
        if snap_gross > 0 and int(inv.total_paise or 0) == expected_net:
            gross_paise += snap_gross
            concession_paise += snap_concession
            for d in discount_lines:
                amt = int(d.get("amount_paise", 0))
                if amt <= 0:
                    continue
                lines.append({
                    "label": d.get("label") or "Concession",
                    "amount": round(amt / 100, 2),
                    "amountPaise": amt,
                })
        else:
            gross_paise += int(inv.total_paise or 0)

    return {
        "grossDue": round(gross_paise / 100, 2),
        "concessionTotal": round(concession_paise / 100, 2),
        "concessions": lines,
    }


def _concession_history(student_user_id) -> list[dict]:
    from apps.fees.models import StudentConcession

    rows = (
        StudentConcession.objects.filter(
            student__student_profile__user_id=student_user_id,
            is_active=True,
        )
        .select_related("rule", "approver")
        .order_by("-decided_at", "-created_at")[:20]
    )
    history = []
    for c in rows:
        history.append({
            "id": str(c.id),
            "ruleName": c.rule.name if c.rule_id else "Concession",
            "amount": round(c.amount_paise / 100, 2),
            "amountPaise": c.amount_paise,
            "status": c.status,
            "appliedAt": c.decided_at.isoformat() if c.decided_at else c.created_at.isoformat(),
            "reason": c.note or "",
        })
    return history


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
    institution_type = "college" if getattr(tenant, "institution_type", "") == "college" else "school"
    exam_invoice_ids = set(
        FeeInvoice.objects.filter(
            student__student_profile__user_id=student_user_id,
            assignment__isnull=True,
            is_active=True,
            lines__kind=FeeComponentKind.EXAM,
        ).values_list("pk", flat=True)
    )
    # One tuition invoice set for both ledger and schedule (avoids mismatched / duplicated fee views).
    tuition_invoices = [
        i for i in list(list_open_invoices_for_student_user(student_user_id))
        if i.pk not in exam_invoice_ids
    ]
    invoices = [i for i in tuition_invoices if is_collectible_outstanding(i)]

    total_due = sum(i.total_paise for i in invoices)
    paid = sum(i.paid_paise for i in invoices)
    balance = sum(i.balance_paise for i in invoices)
    today = datetime.date.today()
    open_due_dates = []
    installment_overdue = False
    for inv in invoices:
        open_installment_dues = []
        for installment in inv.installments.all():
            if installment.paid_paise < installment.amount_paise and installment.due_date:
                open_installment_dues.append(installment.due_date)
                if installment.due_date < today:
                    installment_overdue = True
        if open_installment_dues:
            open_due_dates.extend(open_installment_dues)
        elif inv.balance_paise > 0 and inv.due_date:
            # Prefer installment dues; fall back to invoice due when there are none.
            open_due_dates.append(inv.due_date)
    next_due = min(open_due_dates).isoformat() if open_due_dates else None
    is_overdue = installment_overdue or any(d < today for d in open_due_dates)

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

    breakdown = _concession_breakdown(invoices)
    history = _concession_history(student_user_id)

    return {
        "institutionType": institution_type,
        "ledger": {
            "totalDue": round(total_due / 100, 2),
            "paid": round(paid / 100, 2),
            "balance": round(balance / 100, 2),
            "nextDueDate": next_installment["dueDate"] if next_installment else next_due,
            "isOverdue": is_overdue or any(r["status"] == "overdue" for r in schedule),
            "grossDue": breakdown["grossDue"],
            "concessionTotal": breakdown["concessionTotal"],
            "netPayable": round(balance / 100, 2),
        },
        "concessions": breakdown["concessions"],
        "concessionHistory": history,
        "payments": payments,
        "razorpayKeyId": dj_settings.RAZORPAY_KEY_ID,
        "examFees": _build_exam_fees(student_user_id),
        "installmentSchedule": schedule,
    }
