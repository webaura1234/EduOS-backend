"""Admin Fees overview — the FeesData aggregate the admin screen consumes.

Real data for structures, concession rules/requests, credit notes, refunds,
webhooks, ledger and collection. Domains not yet modelled (credit-note *requests*,
exam-fee invoices, reconciliation) return empty.

Payments are deliberately NOT part of this aggregate (they used to be, unbounded —
see admin_payments_list.py) since a branch's payment history is unbounded and gets
its own paginated/filterable endpoint instead.
"""

import datetime

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.fees.enums import CarryForwardState
from apps.fees.helpers.payment_dict import batch_label as _batch_label
from apps.fees.helpers.payment_dict import class_label as _class_label
from apps.fees.helpers.payment_dict import rupees as _rupees
from apps.fees.helpers.payment_dict import student_name as _student_name
from apps.fees.queries import concession as conc_q
from apps.fees.queries import invoice as inv_q
from apps.fees.queries.invoice import is_collectible_outstanding
from apps.fees.queries import payment as pay_q
from apps.fees.queries import refund as ref_q
from apps.fees.queries import structure as struct_q

_REFUND_STATUS = {"requested": "pending", "approved": "approved", "rejected": "rejected",
                  "processed": "processed", "completed": "processed"}

_PRIOR_YEAR_BALANCE_PREFIX = "Prior Year Balance"


def _current_academic_year_id(branch) -> str | None:
    from apps.academics.models import AcademicYear

    academic_years = list(
        AcademicYear.objects.filter(branch_id=branch.pk, is_active=True).order_by("-start_date")
    )
    current_ay = next((y for y in academic_years if y.is_current), academic_years[0] if academic_years else None)
    return str(current_ay.id) if current_ay else None


def _filtered_invoices(
    branch,
    *,
    academic_year_id=None,
    batch_id=None,
    course_id=None,
):
    qs = inv_q.list_invoices(branch.pk).prefetch_related(
        "installments", "lines", "assignment",
    ).select_related(
        "student__academic_year", "student__batch__course",
        "carried_forward_to__student__academic_year",
    )
    if academic_year_id:
        qs = qs.filter(student__academic_year_id=academic_year_id)
    if batch_id:
        qs = qs.filter(student__batch_id=batch_id)
    if course_id:
        qs = qs.filter(student__batch__course_id=course_id)
    return qs


def _enrollment_row_metadata(enrollment) -> dict:
    if not enrollment:
        return {
            "classLabel": "",
            "academicYearId": None,
            "academicYearLabel": None,
            "batchId": None,
            "courseId": None,
            "courseName": None,
            "sectionName": None,
        }
    batch = enrollment.batch
    course = batch.course if batch and batch.course_id else None
    course_name = course.name if course else ""
    section_name = batch.name if batch else ""
    class_label = _class_label(enrollment)
    year = enrollment.academic_year
    return {
        "classLabel": class_label,
        "academicYearId": str(enrollment.academic_year_id) if enrollment.academic_year_id else None,
        "academicYearLabel": year.name if year else None,
        "batchId": str(enrollment.batch_id) if enrollment.batch_id else None,
        "courseId": str(batch.course_id) if batch and batch.course_id else None,
        "courseName": course_name or None,
        "sectionName": section_name or None,
    }


def _charge_category(kind: str, label: str) -> str:
    if label.startswith(_PRIOR_YEAR_BALANCE_PREFIX):
        return "carry_forward"
    if kind == "exam":
        return "exam"
    return "other"


def _allocate_line_paid(lines, total_paid_paise: int) -> list[int]:
    """Proportional paid_paise per line (last line gets remainder)."""
    if not lines:
        return []
    total_amount = sum(int(line.amount_paise) for line in lines)
    if total_amount <= 0:
        return [0] * len(lines)
    remaining = total_paid_paise
    allocated = []
    for idx, line in enumerate(lines):
        if idx == len(lines) - 1:
            paid = remaining
        else:
            paid = (total_paid_paise * int(line.amount_paise)) // total_amount
            remaining -= paid
        allocated.append(paid)
    return allocated


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
    from apps.admissions.queries.enrollment import enrollments_in_batch
    from apps.fees.interactors.publish import structure_impact

    components = []
    head_names = set()
    for c in (s.components or []):
        paise = c.get("amountPaise", c.get("amount_paise"))
        label = c.get("name", c.get("label", ""))
        head_names.add(label)
        components.append({
            "id": str(c.get("id", "")),
            "name": label,
            "kind": c.get("kind", "other"),
            "amount": _rupees(paise) if paise is not None else c.get("amount", 0),
            "amountPaise": paise,
        })
    installments = _derive_installments_from_components(s.components or [])
    annual_paise = sum(int(c.get("amount_paise", c.get("amountPaise", 0)) or 0) for c in (s.components or []))
    impact = structure_impact(s)
    student_count = enrollments_in_batch(s.batch_id).count() if s.batch_id else 0
    created_by = ""
    if s.created_by_id:
        try:
            created_by = s.created_by.full_name
        except Exception:  # noqa: BLE001
            created_by = ""
    published_by = ""
    if s.published_by_id:
        try:
            published_by = s.published_by.full_name
        except Exception:  # noqa: BLE001
            published_by = ""

    return {
        "id": str(s.id),
        "name": s.name,
        "appliesToLabel": _batch_label(s.batch) if s.batch_id else "",
        "batchId": str(s.batch_id) if s.batch_id else None,
        "academicYearId": str(s.academic_year_id) if s.academic_year_id else None,
        "academicYearLabel": s.academic_year.name if getattr(s, "academic_year", None) else None,
        "components": components,
        "installments": installments,
        "createdAt": s.created_at.isoformat(),
        "updatedAt": s.updated_at.isoformat() if s.updated_at else s.created_at.isoformat(),
        "version": getattr(s, "version", 1),
        "status": getattr(s, "status", "published"),
        "publishedAt": s.published_at.isoformat() if getattr(s, "published_at", None) else None,
        "publishedByName": published_by or None,
        "createdByName": created_by or None,
        "studentCount": student_count,
        "invoiceCount": impact["invoiceCount"],
        "assignmentCount": impact["assignmentCount"],
        "isLocked": impact["isLocked"],
        "annualFee": _rupees(annual_paise),
        "feeHeadCount": len(head_names),
        "matrixComponents": s.components or [],
    }


def _concession_rule(r) -> dict:
    criteria = r.criteria or {}
    return {
        "id": str(r.id),
        "name": r.name,
        "description": criteria.get("description", ""),
        "percentOff": r.percent or 0,
        "amountPaise": r.amount_paise,
        "active": r.is_active,
        "studentsUsing": getattr(r, "students_using", 0) or 0,
        "totalGrantedPaise": getattr(r, "total_granted_paise", 0) or 0,
        "lastAppliedAt": (
            r.last_applied_at.isoformat() if getattr(r, "last_applied_at", None) else None
        ),
    }


def _student_concession(req) -> dict:
    return {
        "id": str(req.id),
        "studentId": str(req.student.student_profile_id) if req.student_id else "",
        "studentName": _student_name(req.student),
        "classLabel": _class_label(req.student),
        "ruleId": str(req.rule_id) if req.rule_id else "",
        "ruleName": req.rule.name if req.rule_id else "",
        "amountPaise": req.amount_paise,
        "amount": _rupees(req.amount_paise),
        "appliedAt": req.decided_at.isoformat() if req.decided_at else req.created_at.isoformat(),
        "appliedBy": str(req.approver_id) if req.approver_id else None,
        "appliedByName": (
            req.approver.full_name or req.approver.email if req.approver else None
        ),
        "reason": req.note or "",
        "status": req.status if req.status in ("active", "revoked", "expired") else "revoked",
        "createdAt": req.created_at.isoformat(),
    }


def _concession_request(req) -> dict:
    """Deprecated alias for admin payload compatibility."""
    return _student_concession(req)


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


def _installment_schedules(
    branch,
    *,
    academic_year_id=None,
    batch_id=None,
    course_id=None,
) -> dict:
    today = datetime.date.today()
    by_student: dict[str, list] = {}
    invoices = _filtered_invoices(
        branch,
        academic_year_id=academic_year_id,
        batch_id=batch_id,
        course_id=course_id,
    )
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
                "label": _installment_label(inv.assignment, inst.sequence),
                "dueDate": due,
                "amount": _rupees(inst.amount_paise),
                "paid": _rupees(inst.paid_paise),
                "status": status,
            })
    return by_student


def _fee_charges_by_student(
    branch,
    *,
    academic_year_id=None,
    batch_id=None,
    course_id=None,
) -> dict:
    by_student: dict[str, list] = {}
    invoices = _filtered_invoices(
        branch,
        academic_year_id=academic_year_id,
        batch_id=batch_id,
        course_id=course_id,
    )
    for inv in invoices:
        enrollment = inv.student
        sid = str(enrollment.student_profile_id) if enrollment else None
        if not sid:
            continue
        inst_list = list(inv.installments.all())
        inst_total = sum(int(i.amount_paise) for i in inst_list)
        lines = list(inv.lines.all())
        due_date = inv.due_date.isoformat() if inv.due_date else None
        year_id = str(enrollment.academic_year_id) if enrollment and enrollment.academic_year_id else ""
        year_label = enrollment.academic_year.name if enrollment and enrollment.academic_year_id else ""

        rows = by_student.setdefault(sid, [])

        if not inst_list:
            paid_alloc = _allocate_line_paid(lines, int(inv.paid_paise))
            for line, line_paid in zip(lines, paid_alloc, strict=False):
                amount_paise = int(line.amount_paise)
                balance_paise = max(amount_paise - line_paid, 0)
                if not is_collectible_outstanding(inv):
                    balance_paise = 0
                label = line.label or ""
                carried_to = None
                if inv.carry_forward_state == "carried_forward" and inv.carried_forward_to_id:
                    target_enrollment = inv.carried_forward_to.student
                    if target_enrollment and target_enrollment.academic_year_id:
                        carried_to = target_enrollment.academic_year.name
                rows.append({
                    "invoiceId": str(inv.id),
                    "academicYearId": year_id,
                    "academicYearLabel": year_label,
                    "label": label,
                    "kind": line.kind or "other",
                    "amount": _rupees(amount_paise),
                    "paid": _rupees(line_paid),
                    "balance": _rupees(balance_paise),
                    "dueDate": due_date,
                    "isCarryForward": label.startswith(_PRIOR_YEAR_BALANCE_PREFIX),
                    "originalStatus": inv.status,
                    "carryForward": inv.carry_forward_state == "carried_forward",
                    "carriedForwardToYearLabel": carried_to,
                    "category": _charge_category(line.kind or "other", label),
                })
        elif int(inv.total_paise) > inst_total:
            remainder = int(inv.total_paise) - inst_total
            if int(inv.total_paise) > 0:
                remainder_paid = (int(inv.paid_paise) * remainder) // int(inv.total_paise)
            else:
                remainder_paid = 0
            rows.append({
                "invoiceId": str(inv.id),
                "academicYearId": year_id,
                "academicYearLabel": year_label,
                "label": "Other charges (not in installments)",
                "kind": "other",
                "amount": _rupees(remainder),
                "paid": _rupees(remainder_paid),
                "balance": _rupees(max(remainder - remainder_paid, 0)),
                "dueDate": due_date,
                "isCarryForward": False,
                "category": "other",
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


def _ledger_and_collection(
    branch,
    *,
    academic_year_id=None,
    batch_id=None,
    course_id=None,
):
    """Group invoices per student into ledger rows; derive the collection snapshot."""
    today = datetime.date.today()
    by_student: dict[str, dict] = {}
    outstanding_total = 0

    for inv in _filtered_invoices(
        branch,
        academic_year_id=academic_year_id,
        batch_id=batch_id,
        course_id=course_id,
    ):
        enrollment = inv.student
        sid = str(enrollment.student_profile_id) if enrollment else "—"
        meta = _enrollment_row_metadata(enrollment)
        row = by_student.setdefault(sid, {
            "studentId": sid,
            "studentName": _student_name(enrollment),
            "classLabel": meta["classLabel"],
            "academicYearId": meta["academicYearId"],
            "academicYearLabel": meta["academicYearLabel"],
            "batchId": meta["batchId"],
            "courseId": meta["courseId"],
            "courseName": meta["courseName"],
            "sectionName": meta["sectionName"],
            "totalDue": 0, "paid": 0, "balance": 0,
            "nextDueDate": None, "isOverdue": False, "escalationLevel": 0,
            "_due_paise": 0, "_paid_paise": 0,
        })
        row["_due_paise"] += inv.total_paise
        row["_paid_paise"] += inv.paid_paise
        if inv.carry_forward_state == CarryForwardState.CARRIED_FORWARD:
            row["_due_paise"] -= inv.total_paise
            row["_paid_paise"] -= inv.paid_paise
        balance = inv.total_paise - inv.paid_paise
        collectible = is_collectible_outstanding(inv)
        if collectible:
            outstanding_total += max(balance, 0)
        if collectible and balance > 0:
                open_inst_dates = [
                    inst.due_date for inst in inv.installments.all()
                    if inst.paid_paise < inst.amount_paise and inst.due_date
                ]
                if open_inst_dates:
                    earliest = min(open_inst_dates)
                    if row["nextDueDate"] is None or earliest.isoformat() < row["nextDueDate"]:
                        row["nextDueDate"] = earliest.isoformat()
                elif inv.due_date:
                    if row["nextDueDate"] is None or inv.due_date.isoformat() < row["nextDueDate"]:
                        row["nextDueDate"] = inv.due_date.isoformat()
                for inst in inv.installments.all():
                    if (
                        inst.paid_paise < inst.amount_paise
                        and inst.due_date
                        and inst.due_date < today
                    ):
                        row["isOverdue"] = True
                        row["escalationLevel"] = max(row["escalationLevel"], 1)
                        break
                if not row["isOverdue"] and inv.due_date and inv.due_date < today:
                    row["isOverdue"] = True
                    row["escalationLevel"] = max(row["escalationLevel"], 1)

    ledger = []
    overdue_count = 0
    for row in by_student.values():
        row["totalDue"] = _rupees(row.pop("_due_paise"))
        row["paid"] = _rupees(row.pop("_paid_paise"))
        row["balance"] = round(row["totalDue"] - row["paid"], 2)
        if row["isOverdue"]:
            overdue_count += 1
        ledger.append(row)

    # Collection snapshot from captured payments (DB-aggregated — no per-row cap).
    month_start = today.replace(day=1)
    collected_today, collected_month = pay_q.collection_snapshot_for_branch(
        branch.pk, today=today, month_start=month_start,
    )

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
        from apps.admissions.queries.enrollment import enrollments_in_batch

        academic_years = list(
            AcademicYear.objects.filter(branch_id=branch.pk, is_active=True).order_by("-start_date")
        )
        current_ay = next((y for y in academic_years if y.is_current), academic_years[0] if academic_years else None)

        batches = []
        for b in list_batches(branch.pk):
            course = b.course if b.course_id else None
            batches.append({
                "id": str(b.id),
                "label": _batch_label(b),
                "studentCount": enrollments_in_batch(b.id).count(),
                "academicYearId": str(b.academic_year_id) if b.academic_year_id else None,
                "academicYearLabel": b.academic_year.name if b.academic_year_id else None,
                "courseId": str(b.course_id) if b.course_id else None,
                "courseName": course.name if course else None,
                "sectionName": b.name or None,
            })

        return Response({
            "institutionType": branch.tenant.institution_type,
            "structures": [_structure(s) for s in struct_q.list_structures(branch.pk)],
            "concessionRules": [_concession_rule(r) for r in conc_q.list_concession_rules(branch.pk)],
            "studentConcessions": [
                _student_concession(r) for r in conc_q.list_student_concessions(branch.pk)
            ],
            "concessionRequests": [
                _concession_request(r) for r in conc_q.list_student_concessions(branch.pk)
            ],
            "creditNotes": [_credit_note(c) for c in conc_q.list_credit_notes(branch.pk)],
            "refunds": [_refund(r) for r in ref_q.list_refunds(branch.pk)],
            "webhooks": [_webhook(w) for w in conc_q.list_webhooks()],
            "ledger": ledger,
            "collection": collection,
            "installmentSchedulesByStudent": _installment_schedules(branch),
            "batches": batches,
            "academicYears": [
                {"id": str(y.id), "name": y.name, "isCurrent": y.is_current}
                for y in academic_years
            ],
            "currentAcademicYearId": str(current_ay.id) if current_ay else None,
            "currentAcademicYearLabel": current_ay.name if current_ay else None,
            "creditNoteRequests": [],
            "examFeeInvoices": [],
            "reconciliation": _reconciliation_list(branch),
        })
