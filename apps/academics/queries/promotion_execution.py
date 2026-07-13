"""Queries — Promotion execution (Phase 3)."""

from django.utils import timezone

from apps.academics.models.promotion import (
    AcademicPromotionExecutionLog,
    AcademicPromotionExecutionRun,
    AcademicPromotionSession,
    ExecutionLogStatus,
    PromotionExecutionStatus,
)


def get_running_session_for_branch(branch_id) -> AcademicPromotionSession | None:
    return (
        AcademicPromotionSession.objects.filter(
            branch_id=branch_id,
            execution_status=PromotionExecutionStatus.RUNNING,
            is_active=True,
        )
        .select_related("source_year", "target_year")
        .first()
    )


def get_latest_run(session_id) -> AcademicPromotionExecutionRun | None:
    return (
        AcademicPromotionExecutionRun.objects.filter(session_id=session_id, is_active=True)
        .order_by("-started_at")
        .first()
    )


def get_run(session_id, run_id) -> AcademicPromotionExecutionRun | None:
    try:
        return AcademicPromotionExecutionRun.objects.get(
            session_id=session_id, pk=run_id, is_active=True
        )
    except (AcademicPromotionExecutionRun.DoesNotExist, ValueError, TypeError):
        return None


def get_run_by_id(run_id) -> AcademicPromotionExecutionRun | None:
    try:
        return AcademicPromotionExecutionRun.objects.select_related(
            "session",
            "session__source_year",
            "session__target_year",
            "session__branch",
            "session__branch__tenant",
            "executed_by",
        ).get(pk=run_id, is_active=True)
    except (AcademicPromotionExecutionRun.DoesNotExist, ValueError, TypeError):
        return None


def create_run(*, session: AcademicPromotionSession, student_total: int, estimated_duration_ms: int, user=None):
    return AcademicPromotionExecutionRun.objects.create(
        session=session,
        status=PromotionExecutionStatus.RUNNING,
        student_total=student_total,
        estimated_duration_ms=estimated_duration_ms,
        estimated_remaining_ms=estimated_duration_ms,
        executed_by=user,
        created_by=user,
        updated_by=user,
    )


def update_run(run: AcademicPromotionExecutionRun, fields: dict, user=None) -> AcademicPromotionExecutionRun:
    for k, v in fields.items():
        setattr(run, k, v)
    if fields:
        run.version += 1
        if user:
            run.updated_by = user
        run.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return run


def create_log(*, run, decision, action, status, **kwargs) -> AcademicPromotionExecutionLog:
    return AcademicPromotionExecutionLog.objects.create(
        run=run,
        decision=decision,
        action=action,
        status=status,
        prior_enrollment_id=kwargs.get("prior_enrollment_id"),
        new_enrollment_id=kwargs.get("new_enrollment_id"),
        fee_assignment_id=kwargs.get("fee_assignment_id"),
        opening_balance_paise=kwargs.get("opening_balance_paise", 0),
        error_message=kwargs.get("error_message", ""),
        created_by=kwargs.get("user"),
        updated_by=kwargs.get("user"),
    )


def list_failed_logs(run_id):
    return AcademicPromotionExecutionLog.objects.filter(
        run_id=run_id,
        status=ExecutionLogStatus.FAILED,
        is_active=True,
    ).select_related("decision", "decision__student_profile")


def get_log_for_decision(run_id, decision_id) -> AcademicPromotionExecutionLog | None:
    try:
        return AcademicPromotionExecutionLog.objects.get(
            run_id=run_id, decision_id=decision_id, is_active=True
        )
    except (AcademicPromotionExecutionLog.DoesNotExist, ValueError, TypeError):
        return None
