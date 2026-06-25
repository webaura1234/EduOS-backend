"""Admin Fees overview — the FeesData aggregate the admin screen consumes.

Real data for structures, concession rules/requests, payments, credit notes, refunds,
webhooks, ledger and collection. Domains not yet modelled (credit-note *requests*,
exam-fee invoices, reconciliation) return empty.
"""

import datetime

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.fees.queries import concession as conc_q
from apps.fees.queries import invoice as inv_q
from apps.fees.queries import payment as pay_q
from apps.fees.queries import refund as ref_q
from apps.fees.queries import structure as struct_q

_PAY_METHOD = {
    "razorpay": "upi",
    "bank_transfer": "upi",
    "cheque": "cash",
    "cash": "cash",
    "upi": "upi",
    "card": "card",
    "netbanking": "netbanking",
}
_PAY_STATUS = {"captured": "captured", "failed": "failed", "refunded": "refunded",
               "created": "pending", "authorized": "pending", "pending": "pending"}
_REFUND_STATUS = {"requested": "pending", "approved": "approved", "rejected": "rejected",
                  "processed": "processed", "completed": "processed"}


def _rupees(paise) -> float:
    return round((paise or 0) / 100, 2)


def _student_name(enrollment) -> str:
    try:
        return enrollment.user.full_name
    except Exception:
        return ""


def _class_label(enrollment) -> str:
    if not enrollment or not enrollment.current_batch_id:
        return ""
    batch = enrollment.current_batch
    return _batch_label(batch)


def _batch_label(batch) -> str:
    if batch is None:
        return ""
    course = getattr(batch, "course", None)
    course_name = course.name if course else ""
    section = batch.name or ""
    if course_name and section:
        return f"{course_name} - {section}"
    return course_name or section


def _derive_installments_from_components(components: list) -> list:
    groups: dict[int, dict] = {}
    for c in components or []:
        inst_no = int(c.get("installment_no", 1))
        paise = c.get("amount_paise", c.get("amountPaise", 0)) or 0
        bucket = groups.setdefault(inst_no, {"amount_paise": 0, "due_dates": [], "labels": []})
        bucket["amount_paise"] += int(paise)
        if c.get("due_date"):
            bucket["due_dates"].append(c["due_date"])
        label = c.get("label") or c.get("name") or ""
        if label:
            bucket["labels"].append(label)
    installments = []
    for inst_no in sorted(groups.keys()):
        g = groups[inst_no]
        due = max(g["due_dates"]) if g["due_dates"] else ""
        label = g["labels"][0] if g["labels"] else f"Installment {inst_no}"
        installments.append({
            "id": f"inst-{inst_no}",
            "label": label,
            "dueDate": due,
            "amount": _rupees(g["amount_paise"]),
            "amountPaise": g["amount_paise"],
        })
    return installments


def _structure(s) -> dict:
    components = []
    for c in (s.components or []):
        paise = c.get("amountPaise", c.get("amount_paise"))
        components.append({
            "id": str(c.get("id", "")),
            "name": c.get("name", c.get("label", "")),
            "kind": c.get("kind", "other"),
            "amount": _rupees(paise) if paise is not None else c.get("amount", 0),
            "amountPaise": paise,
        })
    return {
        "id": str(s.id),
        "name": s.name,
        "appliesToLabel": _batch_label(s.batch) if s.batch_id else "",
        "batchId": str(s.batch_id) if s.batch_id else None,
        "academicYearId": str(s.academic_year_id) if s.academic_year_id else None,
        "components": components,
        "installments": _derive_installments_from_components(s.components or []),
        "createdAt": s.created_at.isoformat(),
        "version": getattr(s, "version", 1),
    }


def _concession_rule(r) -> dict:
    return {
        "id": str(r.id),
        "name": r.name,
        "description": "",
        "percentOff": r.percent or 0,
        "requiresApproval": True,
        "active": r.is_active,
    }


def _concession_request(req) -> dict:
    return {
        "id": str(req.id),
        "studentId": str(req.student.student_profile_id) if req.student_id else "",
        "studentName": _student_name(req.student),
        "classLabel": _class_label(req.student),
        "ruleId": str(req.rule_id) if req.rule_id else "",
        "ruleName": req.rule.name if req.rule_id else "",
        "requestedAt": req.created_at.isoformat(),
        "status": req.status if req.status in ("pending", "approved", "rejected") else "pending",
        "reviewedAt": req.decided_at.isoformat() if req.decided_at else None,
        "reviewNote": req.note or None,
    }


def _payment(p) -> dict:
    inv = p.invoice
    enrollment = inv.student if inv else None
    receipt = getattr(p, "receipt", None)
    return {
        "id": str(p.id),
        "studentId": str(enrollment.student_profile_id) if enrollment else "",
        "studentName": _student_name(enrollment),
        "classLabel": _class_label(enrollment),
        "paidAt": p.captured_at.isoformat() if p.captured_at else p.created_at.isoformat(),
        "amount": _rupees(p.amount_paise),
        "amountPaise": p.amount_paise,
        "method": _PAY_METHOD.get(p.method, "cash"),
        "reference": p.razorpay_payment_id or "",
        "receiptNo": str(receipt.sequence_number) if receipt else "",
        "orderId": p.razorpay_order_id or "",
        "status": _PAY_STATUS.get(p.status, "pending"),
        "source": "gateway" if p.method == "razorpay" else "manual",
        "invoiceId": str(p.invoice_id) if p.invoice_id else "",
    }


def _credit_note(c) -> dict:
    return {
        "id": str(c.id),
        "studentId": str(c.student.student_profile_id) if c.student_id else "",
        "studentName": _student_name(c.student),
        "classLabel": _class_label(c.student),
        "amount": _rupees(c.amount_paise),
        "amountPaise": c.amount_paise,
        "reason": c.reason,
        "createdAt": c.created_at.isoformat(),
        "status": "void" if c.status == "rejected" else "active",
    }


def _refund(r) -> dict:
    payment = r.payment
    enrollment = payment.invoice.student if payment and payment.invoice_id else None
    return {
        "id": str(r.id),
        "paymentId": str(r.payment_id),
        "studentName": _student_name(enrollment),
        "amount": _rupees(r.amount_paise),
        "amountPaise": r.amount_paise,
        "reason": r.reason,
        "status": _REFUND_STATUS.get(r.status, "pending"),
        "requestedAt": r.created_at.isoformat(),
        "reviewedAt": None,
        "reviewNote": None,
    }


def _webhook(w) -> dict:
    event_type = (w.payload or {}).get("event", "payment.captured")
    return {
        "id": str(w.id),
        "provider": "razorpay",
        "eventType": event_type if event_type in (
            "payment.captured", "payment.failed", "refund.processed"
        ) else "payment.captured",
        "receivedAt": w.created_at.isoformat(),
        "signatureVerified": True,
        "idempotencyKey": w.event_id,
        "status": "processed" if w.processed_at else "failed",
        "note": "",
    }


def _installment_schedules(branch) -> dict:
    today = datetime.date.today()
    by_student: dict[str, list] = {}
    invoices = inv_q.list_invoices(branch.pk).prefetch_related("installments")
    for inv in invoices:
        enrollment = inv.student
        sid = str(enrollment.student_profile_id) if enrollment else None
        if not sid:
            continue
        rows = by_student.setdefault(sid, [])
        for inst in inv.installments.all().order_by("sequence"):
            due = inst.due_date.isoformat() if inst.due_date else ""
            status = inst.status or "due"
            if (
                status != "paid"
                and inst.due_date
                and inst.due_date < today
                and inst.paid_paise < inst.amount_paise
            ):
                status = "overdue"
            rows.append({
                "sequence": inst.sequence,
                "label": f"Installment {inst.sequence}",
                "dueDate": due,
                "amount": _rupees(inst.amount_paise),
                "paid": _rupees(inst.paid_paise),
                "status": status,
            })
    return by_student


def _reconciliation_list(branch) -> list:
    from django.utils import timezone
    from datetime import timedelta

    cutoff = timezone.now() - timedelta(minutes=5)
    items = []
    for p in pay_q.list_pending_payments_for_branch(branch.pk, cutoff):
        enrollment = p.invoice.student if p.invoice_id else None
        items.append({
            "orderId": p.razorpay_order_id or str(p.id),
            "paymentId": p.razorpay_payment_id or None,
            "status": "pending",
            "lastCheckedAt": p.updated_at.isoformat(),
            "note": f"{_student_name(enrollment)} · ₹{_rupees(p.amount_paise)}",
        })
    return items


def _ledger_and_collection(branch):
    """Group invoices per student into ledger rows; derive the collection snapshot."""
    today = datetime.date.today()
    by_student: dict[str, dict] = {}
    outstanding_total = 0

    for inv in inv_q.list_invoices(branch.pk):
        enrollment = inv.student
        sid = str(enrollment.student_profile_id) if enrollment else "—"
        row = by_student.setdefault(sid, {
            "studentId": sid,
            "studentName": _student_name(enrollment),
            "classLabel": _class_label(enrollment),
            "totalDue": 0, "paid": 0, "balance": 0,
            "nextDueDate": None, "isOverdue": False, "escalationLevel": 0,
            "_due_paise": 0, "_paid_paise": 0,
        })
        row["_due_paise"] += inv.total_paise
        row["_paid_paise"] += inv.paid_paise
        balance = inv.total_paise - inv.paid_paise
        outstanding_total += max(balance, 0)
        if balance > 0 and inv.due_date:
            if row["nextDueDate"] is None or inv.due_date.isoformat() < row["nextDueDate"]:
                row["nextDueDate"] = inv.due_date.isoformat()
            if inv.due_date < today:
                row["isOverdue"] = True
                row["escalationLevel"] = 1

    ledger = []
    overdue_count = 0
    for row in by_student.values():
        row["totalDue"] = _rupees(row.pop("_due_paise"))
        row["paid"] = _rupees(row.pop("_paid_paise"))
        row["balance"] = round(row["totalDue"] - row["paid"], 2)
        if row["isOverdue"]:
            overdue_count += 1
        ledger.append(row)

    # Collection snapshot from captured payments.
    month_start = today.replace(day=1)
    collected_today = collected_month = 0
    for p in pay_q.list_payments_for_branch(branch.pk, limit=1000):
        if p.status != "captured":
            continue
        when = (p.captured_at or p.created_at).date()
        if when == today:
            collected_today += p.amount_paise
        if when >= month_start:
            collected_month += p.amount_paise

    collection = {
        "collectedToday": _rupees(collected_today),
        "collectedThisMonth": _rupees(collected_month),
        "outstandingTotal": _rupees(outstanding_total),
        "overdueCount": overdue_count,
        "updatedAt": datetime.datetime.now().isoformat(),
    }
    return ledger, collection


class AdminFeesOverviewView(APIView):
    """GET → FeesData (full fees aggregate for the admin screen)."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        ledger, collection = _ledger_and_collection(branch)

        from apps.academics.models import AcademicYear
        from apps.academics.queries.structure import list_batches

        academic_years = list(
            AcademicYear.objects.filter(branch_id=branch.pk, is_active=True).order_by("-start_date")
        )
        current_ay = next((y for y in academic_years if y.is_current), academic_years[0] if academic_years else None)

        return Response({
            "institutionType": branch.tenant.institution_type,
            "structures": [_structure(s) for s in struct_q.list_structures(branch.pk)],
            "concessionRules": [_concession_rule(r) for r in conc_q.list_concession_rules(branch.pk)],
            "concessionRequests": [
                _concession_request(r) for r in conc_q.list_concession_requests(branch.pk)
            ],
            "payments": [_payment(p) for p in pay_q.list_payments_for_branch(branch.pk)],
            "creditNotes": [_credit_note(c) for c in conc_q.list_credit_notes(branch.pk)],
            "refunds": [_refund(r) for r in ref_q.list_refunds(branch.pk)],
            "webhooks": [_webhook(w) for w in conc_q.list_webhooks()],
            "ledger": ledger,
            "collection": collection,
            "installmentSchedulesByStudent": _installment_schedules(branch),
            "batches": [{"id": str(b.id), "label": _batch_label(b)} for b in list_batches(branch.pk)],
            "currentAcademicYearId": str(current_ay.id) if current_ay else None,
            "creditNoteRequests": [],
            "examFeeInvoices": [],
            "reconciliation": _reconciliation_list(branch),
        })
