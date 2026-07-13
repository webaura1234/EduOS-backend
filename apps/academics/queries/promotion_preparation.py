"""Queries — Academic year promotion preparation (Phase 2)."""

from django.utils import timezone

from apps.academics.models.promotion import (
    AcademicPromotionClassMapping,
    AcademicPromotionDecision,
    AcademicPromotionPreparationLog,
    AcademicPromotionSession,
    ExecutionReadiness,
    PreparationLogEvent,
    PreparationStatus,
    PromotionSessionStatus,
)


def require_approved_session(branch_id, session_id) -> AcademicPromotionSession | None:
    try:
        return AcademicPromotionSession.objects.select_related(
            "source_year", "target_year", "branch", "approved_by", "preparation_locked_by"
        ).get(
            branch_id=branch_id,
            pk=session_id,
            status=PromotionSessionStatus.APPROVED,
            is_active=True,
        )
    except (AcademicPromotionSession.DoesNotExist, ValueError, TypeError):
        return None


def list_class_mappings(session_id):
    return AcademicPromotionClassMapping.objects.filter(session_id=session_id, is_active=True).order_by(
        "source_course_name"
    )


def get_class_mapping(session_id, source_course_id) -> AcademicPromotionClassMapping | None:
    try:
        return AcademicPromotionClassMapping.objects.get(
            session_id=session_id, source_course_id=source_course_id, is_active=True
        )
    except (AcademicPromotionClassMapping.DoesNotExist, ValueError, TypeError):
        return None


def bulk_upsert_class_mappings(session_id, rows: list[dict], user=None):
    for row in rows:
        AcademicPromotionClassMapping.objects.update_or_create(
            session_id=session_id,
            source_course_id=row["source_course_id"],
            defaults={
                "source_course_name": row.get("source_course_name", ""),
                "target_course_id": row["target_course_id"],
                "target_course_name": row.get("target_course_name", ""),
                "updated_by": user,
                "is_active": True,
            },
        )


def update_session(session: AcademicPromotionSession, fields: dict, user=None) -> AcademicPromotionSession:
    for k, v in fields.items():
        setattr(session, k, v)
    session.version += 1
    if user:
        session.updated_by = user
    session.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return session


def list_decisions_with_profile(session_id):
    return (
        AcademicPromotionDecision.objects.filter(session_id=session_id, is_active=True)
        .select_related("student_profile", "student_profile__user")
        .order_by("student_name")
    )


def list_blocked_decisions(session_id, *, page=1, page_size=50):
    qs = AcademicPromotionDecision.objects.filter(
        session_id=session_id,
        is_active=True,
        execution_readiness=ExecutionReadiness.BLOCKED,
    ).order_by("student_name")
    total = qs.count()
    offset = (max(page, 1) - 1) * page_size
    return qs[offset : offset + page_size], total


def count_readiness(session_id) -> dict:
    ready = AcademicPromotionDecision.objects.filter(
        session_id=session_id, is_active=True, execution_readiness=ExecutionReadiness.READY
    ).count()
    blocked = AcademicPromotionDecision.objects.filter(
        session_id=session_id, is_active=True, execution_readiness=ExecutionReadiness.BLOCKED
    ).count()
    return {"ready": ready, "blocked": blocked, "total": ready + blocked}


def create_preparation_log(*, session, event, actor=None, reason="", details=None):
    return AcademicPromotionPreparationLog.objects.create(
        session=session,
        event=event,
        actor=actor,
        reason=reason,
        details=details or {},
        created_by=actor,
        updated_by=actor,
    )


def preparation_mappings_editable(session: AcademicPromotionSession) -> bool:
    return session.preparation_status in (
        PreparationStatus.NOT_STARTED,
        PreparationStatus.IN_PROGRESS,
        PreparationStatus.INVALID,
    )
