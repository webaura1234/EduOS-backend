"""Queries — ConcessionRule, StudentConcession, and CreditNote."""

from django.db.models import Count, Max, Q, Sum

from apps.fees.enums import StudentConcessionStatus
from apps.fees.models import (
    CreditNote,
    StudentConcession,
    ConcessionRule,
    WebhookEventLog,
)

# Backward-compatible alias
ConcessionRequest = StudentConcession


def list_webhooks(*, limit=100):
    """Recent Razorpay webhook events (global; not branch-scoped)."""
    return WebhookEventLog.objects.filter(is_active=True).order_by("-created_at")[:limit]


def list_active_concessions_for_profile(*, branch_id, profile_id):
    return StudentConcession.objects.filter(
        branch_id=branch_id,
        student__student_profile_id=profile_id,
        status=StudentConcessionStatus.ACTIVE,
        is_active=True,
    ).select_related("rule", "student")


def list_active_concessions_for_student(student_id):
    """Active concessions for a student profile (resolved from enrollment id)."""
    try:
        from apps.admissions.models import StudentEnrollment
        enrollment = StudentEnrollment.objects.filter(pk=student_id, is_active=True).only(
            "branch_id", "student_profile_id",
        ).first()
    except (ValueError, TypeError):
        enrollment = None
    if not enrollment:
        return StudentConcession.objects.none()
    return list_active_concessions_for_profile(
        branch_id=enrollment.branch_id,
        profile_id=enrollment.student_profile_id,
    )


def list_approved_requests_for_student(student_id):
    """Backward-compatible alias for assignment/invoice paths."""
    return list_active_concessions_for_student(student_id)


def get_student_concession_for_update(concession_id) -> StudentConcession | None:
    return StudentConcession.objects.select_for_update().filter(pk=concession_id, is_active=True).first()


def get_concession_request_for_update(request_id) -> StudentConcession | None:
    return get_student_concession_for_update(request_id)


def get_credit_note_for_update(credit_note_id) -> CreditNote | None:
    return CreditNote.objects.select_for_update().filter(pk=credit_note_id, is_active=True).first()


# ── Concession Rules ─────────────────────────────────────────────────────────
def list_concession_rules(branch_id):
    active_filter = Q(
        student_concessions__status=StudentConcessionStatus.ACTIVE,
        student_concessions__is_active=True,
    )
    return (
        ConcessionRule.objects.filter(branch_id=branch_id, is_active=True)
        .annotate(
            students_using=Count(
                "student_concessions__student__student_profile_id",
                filter=active_filter,
                distinct=True,
            ),
            total_granted_paise=Sum("student_concessions__amount_paise", filter=active_filter),
            last_applied_at=Max("student_concessions__decided_at", filter=active_filter),
        )
        .order_by("name")
    )


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


def update_concession_rule(rule: ConcessionRule, fields: dict, user=None) -> ConcessionRule:
    for k, v in fields.items():
        setattr(rule, k, v)
    if user:
        rule.updated_by = user
    update_fields = list(fields.keys()) + ["updated_at"]
    if user:
        update_fields.append("updated_by")
    rule.save(update_fields=update_fields)
    return rule


def count_active_concessions_for_rule(rule_id) -> int:
    return StudentConcession.objects.filter(
        rule_id=rule_id, status=StudentConcessionStatus.ACTIVE, is_active=True,
    ).count()


# ── Student Concessions ──────────────────────────────────────────────────────
def list_student_concessions(branch_id, status=None):
    qs = StudentConcession.objects.filter(branch_id=branch_id, is_active=True).select_related(
        "student", "student__student_profile__user", "student__batch",
        "rule", "requested_by", "approver",
    )
    if status:
        qs = qs.filter(status=status)
    return qs.order_by("-decided_at", "-created_at")


def list_concession_requests(branch_id, status=None):
    return list_student_concessions(branch_id, status=status)


def get_student_concession(branch_id, concession_id) -> StudentConcession | None:
    try:
        return StudentConcession.objects.select_related(
            "student", "rule", "requested_by", "approver",
        ).get(branch_id=branch_id, pk=concession_id, is_active=True)
    except (StudentConcession.DoesNotExist, ValueError, TypeError):
        return None


def get_concession_request(branch_id, request_id) -> StudentConcession | None:
    return get_student_concession(branch_id, request_id)


def has_active_concession_for_profile(*, branch_id, profile_id, rule_id) -> bool:
    return StudentConcession.objects.filter(
        branch_id=branch_id,
        student__student_profile_id=profile_id,
        rule_id=rule_id,
        status=StudentConcessionStatus.ACTIVE,
        is_active=True,
    ).exists()


def has_active_concession_for_rule(*, student_id, rule_id) -> bool:
    """Backward-compatible wrapper — checks by student profile, not enrollment row."""
    try:
        from apps.admissions.models import StudentEnrollment
        enrollment = StudentEnrollment.objects.filter(pk=student_id, is_active=True).only(
            "branch_id", "student_profile_id",
        ).first()
    except (ValueError, TypeError):
        return False
    if not enrollment:
        return False
    return has_active_concession_for_profile(
        branch_id=enrollment.branch_id,
        profile_id=enrollment.student_profile_id,
        rule_id=rule_id,
    )


def create_student_concession(
    *,
    branch,
    student,
    rule=None,
    amount_paise,
    requested_by,
    status=StudentConcessionStatus.ACTIVE,
    note="",
    approver=None,
    decided_at=None,
    user=None,
) -> StudentConcession:
    return StudentConcession.objects.create(
        branch=branch,
        student=student,
        rule=rule,
        amount_paise=amount_paise,
        status=status,
        requested_by=requested_by,
        approver=approver,
        decided_at=decided_at,
        note=note,
        created_by=user,
        updated_by=user,
    )


def create_concession_request(**kwargs) -> StudentConcession:
    return create_student_concession(**kwargs)


def update_student_concession(concession: StudentConcession, fields: dict, user=None) -> StudentConcession:
    for k, v in fields.items():
        setattr(concession, k, v)
    if user:
        concession.updated_by = user
    update_fields = list(fields.keys()) + ["updated_at"]
    if user:
        update_fields.append("updated_by")
    concession.save(update_fields=update_fields)
    return concession


def update_concession_request(concession: StudentConcession, fields: dict, user=None) -> StudentConcession:
    return update_student_concession(concession, fields, user=user)


# ── Credit Notes ─────────────────────────────────────────────────────────────
def list_credit_notes(branch_id, student_id=None):
    qs = CreditNote.objects.filter(branch_id=branch_id, is_active=True).select_related(
        "student", "student__student_profile__user", "student__batch",
        "invoice", "approved_by",
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
