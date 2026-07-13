"""Queries — Academic year promotion workspace."""

from django.db.models import Count
from django.utils import timezone

from apps.academics.models.promotion import (
    AcademicPromotionDecision,
    AcademicPromotionOverrideLog,
    AcademicPromotionSession,
    PromotionAction,
    PromotionSessionStatus,
)


def get_draft_session(branch_id, source_year_id) -> AcademicPromotionSession | None:
    return (
        AcademicPromotionSession.objects.filter(
            branch_id=branch_id,
            source_year_id=source_year_id,
            status=PromotionSessionStatus.DRAFT,
            is_active=True,
        )
        .select_related("source_year", "target_year", "branch")
        .first()
    )


def get_approved_session(branch_id, source_year_id) -> AcademicPromotionSession | None:
    return (
        AcademicPromotionSession.objects.filter(
            branch_id=branch_id,
            source_year_id=source_year_id,
            status=PromotionSessionStatus.APPROVED,
            is_active=True,
        )
        .select_related("source_year", "target_year", "branch", "approved_by")
        .first()
    )


def get_current_session_for_branch(branch_id, *, source_year_id) -> AcademicPromotionSession | None:
    """Prefer DRAFT over APPROVED for the current source year."""
    draft = get_draft_session(branch_id, source_year_id)
    if draft:
        return draft
    return get_approved_session(branch_id, source_year_id)


def get_session(branch_id, session_id) -> AcademicPromotionSession | None:
    try:
        return AcademicPromotionSession.objects.select_related(
            "source_year", "target_year", "branch", "approved_by"
        ).get(branch_id=branch_id, pk=session_id, is_active=True)
    except (AcademicPromotionSession.DoesNotExist, ValueError, TypeError):
        return None


def create_session(*, branch, source_year, target_year, user=None) -> AcademicPromotionSession:
    return AcademicPromotionSession.objects.create(
        branch=branch,
        source_year=source_year,
        target_year=target_year,
        status=PromotionSessionStatus.DRAFT,
        created_by=user,
        updated_by=user,
    )


def approve_session(session: AcademicPromotionSession, *, user=None) -> AcademicPromotionSession:
    session.status = PromotionSessionStatus.APPROVED
    session.approved_at = timezone.now()
    session.approved_by = user
    session.version += 1
    if user:
        session.updated_by = user
    session.save(
        update_fields=[
            "status",
            "approved_at",
            "approved_by",
            "version",
            "updated_by",
            "updated_at",
        ]
    )
    return session


def reopen_session(session: AcademicPromotionSession, *, user=None) -> AcademicPromotionSession:
    """Revert an approved session to draft so decisions can be edited again."""
    from apps.academics.models.promotion import PreparationStatus

    session.status = PromotionSessionStatus.DRAFT
    session.approved_at = None
    session.approved_by = None
    session.preparation_status = PreparationStatus.NOT_STARTED
    session.preparation_started_at = None
    session.preparation_locked_at = None
    session.preparation_locked_by = None
    session.validation_snapshot = {}
    session.execution_preview_snapshot = {}
    session.lock_fingerprint = {}
    session.staleness_detected_at = None
    session.version += 1
    if user:
        session.updated_by = user
    session.save(
        update_fields=[
            "status",
            "approved_at",
            "approved_by",
            "preparation_status",
            "preparation_started_at",
            "preparation_locked_at",
            "preparation_locked_by",
            "validation_snapshot",
            "execution_preview_snapshot",
            "lock_fingerprint",
            "staleness_detected_at",
            "version",
            "updated_by",
            "updated_at",
        ]
    )
    return session


def clear_decision_validation_state(session_id) -> None:
    """Drop Phase-2 readiness fields so validation runs fresh after review reopens."""
    AcademicPromotionDecision.objects.filter(session_id=session_id).update(
        execution_readiness=None,
        block_reasons=[],
        target_course_id=None,
        target_course_name="",
        target_batch_id=None,
        target_section_name="",
        target_fee_structure_id=None,
        target_fee_structure_name="",
    )


def delete_decisions_for_session(session_id):
    AcademicPromotionDecision.objects.filter(session_id=session_id).delete()


def bulk_create_decisions(decisions: list[AcademicPromotionDecision]):
    return AcademicPromotionDecision.objects.bulk_create(decisions, batch_size=500)


def list_decisions(session_id, *, branch_id=None, course_id=None, batch_id=None, action=None):
    qs = AcademicPromotionDecision.objects.filter(session_id=session_id, is_active=True)
    if branch_id:
        qs = qs.filter(branch_id_snapshot=branch_id)
    if course_id:
        qs = qs.filter(course_id=course_id)
    if batch_id:
        qs = qs.filter(batch_id=batch_id)
    if action:
        qs = qs.filter(final_action=action)
    return qs.order_by("student_name")


def get_decision(session_id, decision_id) -> AcademicPromotionDecision | None:
    try:
        return AcademicPromotionDecision.objects.get(
            session_id=session_id, pk=decision_id, is_active=True
        )
    except (AcademicPromotionDecision.DoesNotExist, ValueError, TypeError):
        return None


def update_decision(decision: AcademicPromotionDecision, fields: dict, user=None) -> AcademicPromotionDecision:
    for k, v in fields.items():
        setattr(decision, k, v)
    decision.version += 1
    if user:
        decision.updated_by = user
    decision.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return decision


def create_override_log(*, session, decision, actor, from_action, to_action, reason) -> AcademicPromotionOverrideLog:
    return AcademicPromotionOverrideLog.objects.create(
        session=session,
        decision=decision,
        actor=actor,
        from_action=from_action,
        to_action=to_action,
        reason=reason,
        created_by=actor,
        updated_by=actor,
    )


def count_by_final_action(session_id) -> dict[str, int]:
    rows = (
        AcademicPromotionDecision.objects.filter(session_id=session_id, is_active=True)
        .values("final_action")
        .annotate(count=Count("id"))
    )
    counts = {a.value: 0 for a in PromotionAction}
    total = 0
    for row in rows:
        counts[row["final_action"]] = row["count"]
        total += row["count"]
    counts["total"] = total
    return counts


def list_all_decisions(session_id):
    return list(
        AcademicPromotionDecision.objects.filter(session_id=session_id, is_active=True).order_by("student_name")
    )
