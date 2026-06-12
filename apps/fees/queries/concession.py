"""Queries — ConcessionRule, ConcessionRequest, and CreditNote."""

from apps.fees.enums import ConcessionStatus
from apps.fees.models import ConcessionRequest, ConcessionRule, CreditNote


def list_approved_requests_for_student(student_id):
    return ConcessionRequest.objects.filter(
        student_id=student_id, status=ConcessionStatus.APPROVED, is_active=True
    ).select_related("rule")


def get_concession_request_for_update(request_id) -> ConcessionRequest | None:
    return ConcessionRequest.objects.select_for_update().filter(pk=request_id, is_active=True).first()


def get_credit_note_for_update(credit_note_id) -> CreditNote | None:
    return CreditNote.objects.select_for_update().filter(pk=credit_note_id, is_active=True).first()


# ── Concession Rules ─────────────────────────────────────────────────────────
def list_concession_rules(branch_id):
    return ConcessionRule.objects.filter(branch_id=branch_id, is_active=True).order_by("name")


def get_concession_rule(branch_id, rule_id) -> ConcessionRule | None:
    try:
        return ConcessionRule.objects.get(branch_id=branch_id, pk=rule_id, is_active=True)
    except (ConcessionRule.DoesNotExist, ValueError, TypeError):
        return None


def create_concession_rule(*, branch, name, amount_paise=None, percent=None, criteria=None, user=None) -> ConcessionRule:
    return ConcessionRule.objects.create(
        branch=branch,
        name=name,
        amount_paise=amount_paise,
        percent=percent,
        criteria=criteria or {},
        created_by=user,
        updated_by=user,
    )


# ── Concession Requests ──────────────────────────────────────────────────────
def list_concession_requests(branch_id, status=None):
    qs = ConcessionRequest.objects.filter(branch_id=branch_id, is_active=True).select_related(
        "student", "student__student_profile__user", "rule", "requested_by", "approver"
    )
    if status:
        qs = qs.filter(status=status)
    return qs.order_by("-created_at")


def get_concession_request(branch_id, request_id) -> ConcessionRequest | None:
    try:
        return ConcessionRequest.objects.select_related("student", "rule", "requested_by", "approver").get(
            branch_id=branch_id, pk=request_id, is_active=True
        )
    except (ConcessionRequest.DoesNotExist, ValueError, TypeError):
        return None


def create_concession_request(
    *, branch, student, rule=None, amount_paise, requested_by, status="pending", note="", user=None
) -> ConcessionRequest:
    return ConcessionRequest.objects.create(
        branch=branch,
        student=student,
        rule=rule,
        amount_paise=amount_paise,
        status=status,
        requested_by=requested_by,
        note=note,
        created_by=user,
        updated_by=user,
    )


def update_concession_request(request: ConcessionRequest, fields: dict, user=None) -> ConcessionRequest:
    for k, v in fields.items():
        setattr(request, k, v)
    if user:
        request.updated_by = user
    update_fields = list(fields.keys()) + ["updated_at"]
    if user:
        update_fields.append("updated_by")
    request.save(update_fields=update_fields)
    return request


# ── Credit Notes ─────────────────────────────────────────────────────────────
def list_credit_notes(branch_id, student_id=None):
    qs = CreditNote.objects.filter(branch_id=branch_id, is_active=True).select_related(
        "student", "student__student_profile__user", "invoice", "approved_by"
    )
    if student_id:
        qs = qs.filter(student_id=student_id)
    return qs.order_by("-created_at")


def get_credit_note(branch_id, credit_note_id) -> CreditNote | None:
    try:
        return CreditNote.objects.select_related("student", "invoice", "approved_by").get(
            branch_id=branch_id, pk=credit_note_id, is_active=True
        )
    except (CreditNote.DoesNotExist, ValueError, TypeError):
        return None


def create_credit_note(
    *, branch, student, invoice=None, amount_paise, reason="", status="pending", approved_by=None, user=None
) -> CreditNote:
    return CreditNote.objects.create(
        branch=branch,
        student=student,
        invoice=invoice,
        amount_paise=amount_paise,
        reason=reason,
        status=status,
        approved_by=approved_by,
        created_by=user,
        updated_by=user,
    )


def update_credit_note(credit_note: CreditNote, fields: dict, user=None) -> CreditNote:
    for k, v in fields.items():
        setattr(credit_note, k, v)
    if user:
        credit_note.updated_by = user
    update_fields = list(fields.keys()) + ["updated_at"]
    if user:
        update_fields.append("updated_by")
    credit_note.save(update_fields=update_fields)
    return credit_note
