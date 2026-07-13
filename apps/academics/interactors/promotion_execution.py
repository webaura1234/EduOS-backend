"""Promotion execution orchestrator (Phase 3)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import time

logger = logging.getLogger(__name__)

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.academics.exceptions import PromotionExecutionInProgressError
from apps.academics.interactors import promotion_module_adapters as mod_i
from apps.academics.interactors import promotion_preparation as prep_i
from apps.academics.interactors import promotion_staleness as stale_i
from apps.academics.interactors.year_transition import (
    activate_target_year,
    complete_timetable_rollover,
    deactivate_source_enrollment,
)
from apps.academics.models import RolloverRunStatus
from apps.academics.models.promotion import (
    ExecutionLogStatus,
    ExecutionReadiness,
    PreparationLogEvent,
    PreparationStatus,
    PromotionAction,
    PromotionExecutionStatus,
    PromotionSessionStatus,
)
from apps.academics.queries import promotion as prom_q
from apps.academics.queries import promotion_execution as exec_q
from apps.academics.queries import promotion_preparation as prep_q
from apps.academics.queries import rollover as rol_q
from apps.academics.queries import structure as struct_q
from apps.accounts.models.profile import AcademicStatus
from apps.admissions.enums import EnrollmentStatus
from apps.admissions.queries import enrollment as enr_q
from apps.examinations.queries import marks as exam_marks_q
from apps.fees.interactors.promotion_carry_forward import setup_promotion_fees
from apps.fees.enums import FeeStructureStatus
from apps.fees.queries import structure as fees_q

MS_PER_STUDENT = 250
MIN_DURATION_MS = 30_000

NON_EXECUTABLE = {PromotionAction.PENDING, PromotionAction.MANUAL_REVIEW}


def confirmation_phrase(session) -> str:
    return f"PROMOTE {session.target_year.name}".strip()


def _blocked_count(session) -> int:
    validation = session.validation_snapshot or {}
    students = validation.get("students") or prep_q.count_readiness(session.pk)
    return int(students.get("blocked", 0))


def execution_confirm_token(session) -> str | None:
    snap = session.validation_snapshot or {}
    return snap.get("executionConfirmToken")


def refresh_execution_confirm_token(session, lock_fingerprint: dict, *, user=None) -> str:
    """Bind execution confirmation to the locked validation snapshot."""
    snap = dict(session.validation_snapshot or {})
    payload = {
        "fingerprint": lock_fingerprint,
        "validatedAt": snap.get("validatedAt"),
        "students": snap.get("students"),
    }
    token = hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()
    ).hexdigest()
    snap["executionConfirmToken"] = token
    prep_q.update_session(session, {"validation_snapshot": snap}, user=user)
    return token


def estimate_duration_ms(ready_count: int) -> int:
    return max(MIN_DURATION_MS, ready_count * MS_PER_STUDENT)


def _duration_label(ms: int) -> str:
    minutes = max(1, round(ms / 60_000))
    return f"~{minutes} minute{'s' if minutes != 1 else ''}"


def _require_session(branch_id, session_id):
    session = prep_q.require_approved_session(branch_id, session_id)
    if not session:
        raise ValidationError({"sessionId": "Approved promotion session not found."})
    return session


def _lock_branch_and_session(*, branch_id, session_id):
    from apps.academics.models.promotion import AcademicPromotionSession
    from apps.organizations.models import Branch

    Branch.objects.select_for_update().get(pk=branch_id, is_active=True)
    try:
        return (
            AcademicPromotionSession.objects.select_for_update()
            .select_related("source_year", "target_year", "branch")
            .get(
                pk=session_id,
                branch_id=branch_id,
                status=PromotionSessionStatus.APPROVED,
                is_active=True,
            )
        )
    except AcademicPromotionSession.DoesNotExist:
        raise ValidationError({"sessionId": "Approved promotion session not found."}) from None


def _existing_run_start_payload(session) -> dict | None:
    run = exec_q.get_latest_run(session.pk)
    if not run:
        return None
    payload = _status_payload(run, session)
    payload["estimatedDurationLabel"] = _duration_label(
        payload.get("estimatedDurationMs", run.estimated_duration_ms)
    )
    payload["canLeavePage"] = True
    return payload


def _guard_branch_execution(*, branch_id, session) -> dict | None:
    """Return idempotent payload if this session is already running; else raise 409."""
    running = exec_q.get_running_session_for_branch(branch_id)
    if not running:
        return None
    if running.pk == session.pk:
        return _existing_run_start_payload(session)
    other_run = exec_q.get_latest_run(running.pk)
    raise PromotionExecutionInProgressError(
        running_session_id=running.pk,
        run_id=str(other_run.pk) if other_run else None,
    )


def _assert_no_other_branch_execution(*, branch_id, session) -> None:
    running = exec_q.get_running_session_for_branch(branch_id)
    if running and running.pk != session.pk:
        other_run = exec_q.get_latest_run(running.pk)
        raise PromotionExecutionInProgressError(
            running_session_id=running.pk,
            run_id=str(other_run.pk) if other_run else None,
        )


def pre_execution_checks(session, *, allow_running: bool = False) -> dict:
    if session.status != PromotionSessionStatus.APPROVED:
        raise PermissionDenied("Promotion session must be approved.")
    if session.preparation_status != PreparationStatus.LOCKED:
        raise PermissionDenied("Preparation must be locked before execution.")
    if session.preparation_status == PreparationStatus.INVALID:
        raise PermissionDenied("Preparation is invalid — re-validation required.")

    is_stale, stale_changes = stale_i.check_and_apply_staleness(session)
    session.refresh_from_db()
    if is_stale or session.preparation_status == PreparationStatus.INVALID:
        raise ValidationError(
            {
                "detail": "Preparation Invalid — Re-validation Required",
                "isStale": True,
                "staleChanges": stale_changes,
            }
        )

    audit = prep_i.get_readiness_audit(branch_id=session.branch_id, session_id=session.pk)
    if not audit.get("canProceed"):
        raise ValidationError({"detail": "Session readiness checks failed.", "checks": audit.get("checks", [])})

    if session.execution_status == PromotionExecutionStatus.SUCCEEDED:
        raise ValidationError({"detail": "Promotion has already been executed for this session."})

    if session.execution_status == PromotionExecutionStatus.RUNNING and not allow_running:
        run = exec_q.get_latest_run(session.pk)
        if run:
            return {"existingRunId": str(run.pk), "status": run.status}

    decisions = list(prep_q.list_decisions_with_profile(session.pk))
    ready = [d for d in decisions if d.execution_readiness == ExecutionReadiness.READY]
    if not ready:
        raise ValidationError({"detail": "No ready students to execute."})

    blocked = _blocked_count(session)
    if blocked:
        raise ValidationError(
            {
                "detail": (
                    f"Resolve all blocked students before execution ({blocked} blocked)."
                ),
            }
        )

    for d in ready:
        if d.final_action in (PromotionAction.PROMOTE, PromotionAction.RETAIN):
            if not d.target_batch_id:
                raise ValidationError({"detail": f"Missing destination for {d.student_name}."})
            batch = struct_q.get_batch(session.branch_id, d.target_batch_id)
            if not batch or batch.academic_year_id != session.target_year_id:
                raise ValidationError({"detail": f"Invalid destination batch for {d.student_name}."})
            fee = fees_q.get_structure(session.branch_id, d.target_fee_structure_id)
            if not fee or fee.status != FeeStructureStatus.PUBLISHED:
                raise ValidationError({"detail": f"Missing fee structure for {d.student_name}."})
            target_enr = enr_q.get_active_enrollment_for_profile(
                d.student_profile_id, academic_year_id=session.target_year_id
            )
            if target_enr:
                raise ValidationError({"detail": f"Duplicate target enrollment for {d.student_name}."})

    return {"readyCount": len(ready), "totalCount": len(decisions)}


def get_dry_run(*, branch_id, session_id) -> dict:
    session = _require_session(branch_id, session_id)
    checks = pre_execution_checks(session, allow_running=True)
    preview = session.execution_preview_snapshot or {}
    validation = session.validation_snapshot or {}
    impact = preview.get("executionImpact") or {}
    students = validation.get("students") or preview.get("students") or prep_q.count_readiness(session.pk)
    ready_count = students.get("ready", 0)
    est_ms = estimate_duration_ms(ready_count)
    warnings = []
    if impact.get("outstandingBalancesToCarryForward"):
        warnings.append(
            {
                "label": "Outstanding fees",
                "count": impact["outstandingBalancesToCarryForward"],
            }
        )
    blocked = students.get("blocked", 0)
    block_reason = None
    if blocked:
        block_reason = f"Resolve all blocked students before execution ({blocked} blocked)."
    can_execute = (
        session.execution_status != PromotionExecutionStatus.SUCCEEDED
        and session.preparation_status == PreparationStatus.LOCKED
        and blocked == 0
        and ready_count > 0
        and bool(execution_confirm_token(session))
    )

    return {
        "sessionId": str(session.pk),
        "sourceYearLabel": session.source_year.name,
        "targetYearLabel": session.target_year.name,
        "confirmationPhrase": confirmation_phrase(session),
        "confirmToken": execution_confirm_token(session),
        "students": {
            "total": students.get("ready", 0) + students.get("blocked", 0),
            "ready": ready_count,
            "blocked": blocked,
        },
        "executionImpact": impact,
        "warnings": warnings,
        "blockReason": block_reason,
        "estimatedDurationMs": est_ms,
        "estimatedDurationLabel": _duration_label(est_ms),
        "willRunInBackground": True,
        "canExecute": can_execute,
        "existingRunId": checks.get("existingRunId"),
        "isExecutionRunning": session.execution_status == PromotionExecutionStatus.RUNNING,
    }


@transaction.atomic
def start_execution(
    *,
    branch_id,
    session_id,
    confirmation_phrase_input: str,
    confirm_token: str | None = None,
    user=None,
    request=None,
):
    session = _lock_branch_and_session(branch_id=branch_id, session_id=session_id)

    existing = _guard_branch_execution(branch_id=branch_id, session=session)
    if existing:
        return existing

    expected = confirmation_phrase(session)
    if (confirmation_phrase_input or "").strip().upper() != expected.upper():
        raise ValidationError({"confirmationPhrase": f"Type {expected} to confirm execution."})

    pre_execution_checks(session)

    expected_token = execution_confirm_token(session)
    if not expected_token or (confirm_token or "").strip() != expected_token:
        raise ValidationError(
            {
                "confirmToken": (
                    "Execution confirmation is stale. Reload the dry run and try again."
                ),
            }
        )

    decisions = list(prep_q.list_decisions_with_profile(session.pk))
    ready = [d for d in decisions if d.execution_readiness == ExecutionReadiness.READY]
    est_ms = estimate_duration_ms(len(ready))

    run = exec_q.create_run(
        session=session,
        student_total=len(ready),
        estimated_duration_ms=est_ms,
        user=user,
    )
    prep_q.update_session(
        session,
        {
            "execution_status": PromotionExecutionStatus.RUNNING,
            "executed_by": user,
        },
        user=user,
    )
    prep_q.create_preparation_log(
        session=session,
        event=PreparationLogEvent.EXECUTED,
        actor=user,
        details={"runId": str(run.pk)},
    )

    from apps.academics.tasks import execute_promotion_task

    execute_promotion_task.delay(str(run.pk))

    if user and request:
        from apps.analytics.interactors import audit as audit_i

        audit_i.record_audit(
            tenant=user.tenant,
            actor=user,
            action="promotion.execute.start",
            entity_type="promotion_session",
            entity_id=str(session.pk),
            diff={"runId": str(run.pk), "readyCount": len(ready)},
            request=request,
        )

    return {
        "runId": str(run.pk),
        "status": PromotionExecutionStatus.RUNNING,
        "estimatedDurationMs": est_ms,
        "estimatedDurationLabel": _duration_label(est_ms),
        "canLeavePage": True,
    }


@transaction.atomic
def resume_execution(*, branch_id, session_id, user=None):
    session = _lock_branch_and_session(branch_id=branch_id, session_id=session_id)
    _assert_no_other_branch_execution(branch_id=branch_id, session=session)

    run = exec_q.get_latest_run(session.pk)
    if not run:
        raise ValidationError({"detail": "No execution run to resume."})

    from apps.academics.tasks import execute_promotion_task

    execute_promotion_task.delay(str(run.pk))
    return {"runId": str(run.pk), "status": PromotionExecutionStatus.RUNNING}


def _execute_promote_retain(session, decision, profile, *, user=None):
    source_enr = enr_q.get_active_enrollment_for_profile(
        profile.pk, academic_year_id=session.source_year_id
    )
    if not source_enr:
        raise ValidationError("Missing active source enrollment.")

    backlog = []
    if session.branch.tenant and getattr(session.branch.tenant, "institution_type", "") == "college":
        backlog = exam_marks_q.open_arrear_subjects(source_enr.pk)

    batch = struct_q.get_batch(session.branch_id, decision.target_batch_id)
    new_enr = enr_q.create_enrollment(
        branch=session.branch,
        student_profile=profile,
        batch=batch,
        academic_year=session.target_year,
        backlog_subjects=backlog,
        user=user,
    )
    deactivate_source_enrollment(source_enr, user=user)
    rol_q.set_student_batch(profile, batch.pk, user=user)

    fee_assignment_id = None
    opening = 0
    if decision.target_fee_structure_id:
        fee_assignment_id, opening = setup_promotion_fees(
            branch_id=session.branch_id,
            branch=session.branch,
            new_enrollment=new_enr,
            fee_structure_id=decision.target_fee_structure_id,
            source_enrollment_id=source_enr.pk,
            source_year=session.source_year,
            source_year_label=session.source_year.name,
            promotion_session=session,
            user=user,
        )
    return {
        "prior_enrollment_id": str(source_enr.pk),
        "new_enrollment_id": str(new_enr.pk),
        "fee_assignment_id": fee_assignment_id,
        "opening_balance_paise": opening,
    }


def _execute_graduate(session, decision, profile, *, user=None):
    source_enr = enr_q.get_active_enrollment_for_profile(
        profile.pk, academic_year_id=session.source_year_id
    )
    prior_id = str(source_enr.pk) if source_enr else None
    if source_enr:
        deactivate_source_enrollment(
            source_enr, terminal_status=EnrollmentStatus.GRADUATED, user=user
        )
        rol_q.sync_current_enrollment(profile, source_enr, user=user)
    rol_q.graduate_student(profile, user=user)
    return {"prior_enrollment_id": prior_id, "new_enrollment_id": None}


def _execute_transfer_out(session, decision, profile, *, user=None):
    source_enr = enr_q.get_active_enrollment_for_profile(
        profile.pk, academic_year_id=session.source_year_id
    )
    prior_id = str(source_enr.pk) if source_enr else None
    if source_enr:
        deactivate_source_enrollment(
            source_enr, terminal_status=EnrollmentStatus.TRANSFERRED, user=user
        )
        rol_q.sync_current_enrollment(profile, source_enr, user=user)
    rol_q.set_student_academic_status(profile, status=AcademicStatus.TRANSFERRED, user=user)
    return {"prior_enrollment_id": prior_id, "new_enrollment_id": None}


def _execute_withdrawn(session, decision, profile, *, user=None):
    source_enr = enr_q.get_active_enrollment_for_profile(
        profile.pk, academic_year_id=session.source_year_id
    )
    prior_id = str(source_enr.pk) if source_enr else None
    if source_enr:
        deactivate_source_enrollment(
            source_enr, terminal_status=EnrollmentStatus.WITHDRAWN, user=user
        )
        rol_q.sync_current_enrollment(profile, source_enr, user=user)
    rol_q.set_student_academic_status(profile, status=AcademicStatus.WITHDRAWN, user=user)
    return {"prior_enrollment_id": prior_id, "new_enrollment_id": None}


def _notify_student(session, decision, profile, *, user=None) -> tuple[int, int]:
    from apps.communications.interactors.create import create_notification
    from apps.communications.interactors.recipients import student_and_guardian_users

    template_map = {
        PromotionAction.PROMOTE: "academics.promotion_completed",
        PromotionAction.RETAIN: "academics.promotion_retained",
        PromotionAction.GRADUATE: "academics.promotion_graduated",
        PromotionAction.TRANSFER_OUT: "academics.promotion_transferred",
        PromotionAction.WITHDRAWN: "academics.promotion_withdrawn",
    }
    template = template_map.get(decision.final_action)
    if not template:
        return 0, 0

    variables = {
        "student_name": decision.student_name,
        "from_class": decision.course_name,
        "to_class": decision.target_course_name or decision.course_name,
        "target_year": session.target_year.name,
    }
    sent_count = 0
    failure_count = 0
    for recipient, extras in student_and_guardian_users(profile.user):
        merged = {**variables, **extras}
        try:
            if create_notification(
                template,
                tenant=session.branch.tenant,
                branch=session.branch,
                recipient=recipient,
                variables=merged,
                dedup_key=f"prom:{session.pk}:{decision.pk}:{recipient.pk}",
                related_entity_type="promotion_session",
                related_entity_id=str(session.pk),
            ):
                sent_count += 1
        except Exception:
            failure_count += 1
            logger.exception(
                "Promotion notification failed session=%s decision=%s recipient=%s template=%s",
                session.pk,
                decision.pk,
                recipient.pk,
                template,
            )
    return sent_count, failure_count


def run_execution(*, run_id, user=None):
    """Process all ready decisions for a run (Celery or tests)."""
    run = exec_q.get_run_by_id(run_id)
    if not run:
        return {"error": "run_not_found"}
    session = run.session
    branch = session.branch
    tenant = branch.tenant
    user = user or run.executed_by

    start_ms = time.monotonic()
    decisions = list(prep_q.list_decisions_with_profile(session.pk))
    ready = [d for d in decisions if d.execution_readiness == ExecutionReadiness.READY]
    student_actions: list[dict] = []
    notification_failure_count = 0

    for idx, decision in enumerate(ready):
        profile = decision.student_profile
        exec_q.update_run(
            run,
            {
                "current_decision_id": decision.pk,
                "current_student_name": decision.student_name,
                "processed_count": idx,
                "estimated_remaining_ms": max(
                    0,
                    int(run.estimated_duration_ms * (1 - idx / max(len(ready), 1))),
                ),
            },
            user=user,
        )

        sid = transaction.savepoint()
        try:
            if decision.final_action in NON_EXECUTABLE:
                exec_q.create_log(
                    run=run,
                    decision=decision,
                    action=decision.final_action,
                    status=ExecutionLogStatus.SKIPPED,
                    user=user,
                )
                exec_q.update_run(run, {"skipped_count": run.skipped_count + 1}, user=user)
                transaction.savepoint_commit(sid)
                continue

            if decision.final_action in (PromotionAction.PROMOTE, PromotionAction.RETAIN):
                result = _execute_promote_retain(session, decision, profile, user=user)
                count_field = (
                    "promoted_count"
                    if decision.final_action == PromotionAction.PROMOTE
                    else "retained_count"
                )
                updates = {
                    count_field: getattr(run, count_field) + 1,
                    "processed_count": idx + 1,
                }
                if result.get("fee_assignment_id"):
                    updates["fee_assignments_created"] = run.fee_assignments_created + 1
                if result.get("opening_balance_paise", 0) > 0:
                    updates["opening_balances_carried"] = run.opening_balances_carried + 1
                exec_q.update_run(run, updates, user=user)
            elif decision.final_action == PromotionAction.GRADUATE:
                result = _execute_graduate(session, decision, profile, user=user)
                exec_q.update_run(
                    run,
                    {"graduated_count": run.graduated_count + 1, "processed_count": idx + 1},
                    user=user,
                )
            elif decision.final_action == PromotionAction.TRANSFER_OUT:
                result = _execute_transfer_out(session, decision, profile, user=user)
                exec_q.update_run(
                    run,
                    {"transferred_count": run.transferred_count + 1, "processed_count": idx + 1},
                    user=user,
                )
            elif decision.final_action == PromotionAction.WITHDRAWN:
                result = _execute_withdrawn(session, decision, profile, user=user)
                exec_q.update_run(
                    run,
                    {"withdrawn_count": run.withdrawn_count + 1, "processed_count": idx + 1},
                    user=user,
                )
            else:
                result = {}
                exec_q.update_run(
                    run,
                    {"skipped_count": run.skipped_count + 1, "processed_count": idx + 1},
                    user=user,
                )

            exec_q.create_log(
                run=run,
                decision=decision,
                action=decision.final_action,
                status=ExecutionLogStatus.SUCCEEDED,
                user=user,
                **result,
            )
            _, notify_failures = _notify_student(session, decision, profile, user=user)
            notification_failure_count += notify_failures
            student_actions.append(
                {
                    "decisionId": str(decision.pk),
                    "studentName": decision.student_name,
                    "action": decision.final_action,
                    **result,
                }
            )
            transaction.savepoint_commit(sid)
        except Exception as exc:
            transaction.savepoint_rollback(sid)
            exec_q.create_log(
                run=run,
                decision=decision,
                action=decision.final_action,
                status=ExecutionLogStatus.FAILED,
                error_message=str(exc),
                user=user,
            )
            exec_q.update_run(
                run,
                {"failed_count": run.failed_count + 1, "processed_count": idx + 1},
                user=user,
            )

    run.refresh_from_db()
    flip_ok = run.failed_count == 0 or (run.promoted_count + run.retained_count) > 0
    final_status = PromotionExecutionStatus.SUCCEEDED
    rollover_run = None

    if flip_ok and (run.promoted_count + run.retained_count + run.graduated_count) > 0:
        try:
            with transaction.atomic():
                activate_target_year(
                    branch_id=branch.pk,
                    source_year=session.source_year,
                    target_year=session.target_year,
                    user=user,
                )
                complete_timetable_rollover(
                    branch_id=branch.pk,
                    source_year_id=session.source_year_id,
                    target_year_id=session.target_year_id,
                    user=user,
                )
                rollover_run = rol_q.create_rollover_run(
                    branch=branch,
                    from_year=session.source_year,
                    preview_version=1,
                    user=user,
                )
                rol_q.update_rollover_run(
                    rollover_run,
                    {
                        "status": RolloverRunStatus.SUCCEEDED,
                        "to_year": session.target_year,
                        "snapshot": {"student_actions": student_actions, "promotion_session_id": str(session.pk)},
                        "executed_at": timezone.now(),
                        "executed_by": user,
                    },
                    user=user,
                )
        except Exception as exc:
            final_status = PromotionExecutionStatus.FAILED
            exec_q.update_run(run, {"error_message": str(exc)}, user=user)
    elif run.failed_count > 0:
        final_status = PromotionExecutionStatus.PARTIAL if run.promoted_count + run.retained_count > 0 else PromotionExecutionStatus.FAILED

    elapsed_ms = int((time.monotonic() - start_ms) * 1000)
    blocked_count = sum(
        1 for d in decisions if d.execution_readiness == ExecutionReadiness.BLOCKED
    )
    report = {
        "totalStudents": len(decisions),
        "processed": run.processed_count,
        "promoted": run.promoted_count,
        "retained": run.retained_count,
        "graduated": run.graduated_count,
        "transferred": run.transferred_count,
        "withdrawn": run.withdrawn_count,
        "skipped": run.skipped_count,
        "blocked": blocked_count,
        "failed": run.failed_count,
        "manualReviewPending": sum(1 for d in decisions if d.final_action == PromotionAction.MANUAL_REVIEW),
        "feeAssignmentsCreated": run.fee_assignments_created,
        "openingBalancesCarried": run.opening_balances_carried,
        "executionTimeMs": elapsed_ms,
        "targetYearLabel": session.target_year.name,
        "notificationFailures": notification_failure_count,
        "moduleUpdates": mod_i.run_module_updates(
            branch_id=branch.pk, session_id=session.pk, student_actions=student_actions, user=user
        ),
    }

    exec_q.update_run(
        run,
        {
            "status": final_status,
            "completed_at": timezone.now(),
            "processed_count": len(ready),
            "current_student_name": "",
            "estimated_remaining_ms": 0,
        },
        user=user,
    )
    prep_q.update_session(
        session,
        {
            "execution_status": final_status,
            "executed_at": timezone.now(),
            "execution_report": report,
            "rollover_run": rollover_run,
        },
        user=user,
    )

    if user:
        try:
            from apps.analytics.interactors import audit as audit_i

            audit_i.record_audit(
                tenant=tenant,
                actor=user,
                action="promotion.execute",
                entity_type="promotion_session",
                entity_id=str(session.pk),
                diff=report,
            )
        except Exception:
            pass

    return {"status": final_status, "runId": str(run.pk), "report": report}


def _status_payload(run, session) -> dict:
    total = run.student_total or 1
    processed = run.processed_count
    pct = min(100, int(processed * 100 / total))
    return {
        "runId": str(run.pk),
        "status": run.status,
        "processedCount": processed,
        "studentTotal": run.student_total,
        "percentComplete": pct,
        "currentStudentName": run.current_student_name or "",
        "counts": {
            "promoted": run.promoted_count,
            "retained": run.retained_count,
            "graduated": run.graduated_count,
            "transferred": run.transferred_count,
            "withdrawn": run.withdrawn_count,
            "failed": run.failed_count,
            "skipped": run.skipped_count,
        },
        "estimatedDurationMs": run.estimated_duration_ms,
        "estimatedRemainingMs": run.estimated_remaining_ms,
        "startedAt": run.started_at.isoformat() if run.started_at else None,
        "canLeavePage": True,
        "targetYearLabel": session.target_year.name,
    }


def get_execution_status(*, branch_id, session_id) -> dict:
    session = _require_session(branch_id, session_id)
    run = exec_q.get_latest_run(session.pk)
    if not run:
        return {"status": session.execution_status, "processedCount": 0, "studentTotal": 0}
    return _status_payload(run, session)


def get_execution_report(*, branch_id, session_id) -> dict:
    session = _require_session(branch_id, session_id)
    report = session.execution_report or {}
    return {
        "sessionId": str(session.pk),
        "executionStatus": session.execution_status,
        "executedAt": session.executed_at.isoformat() if session.executed_at else None,
        "targetYearLabel": session.target_year.name,
        "report": report,
        "verification": {
            "singleCurrentYear": True,
            "sourceYearFrozen": session.source_year.is_frozen,
            "targetYearCurrent": session.target_year.is_current,
        },
    }


def export_report_csv(*, branch_id, session_id) -> str:
    data = get_execution_report(branch_id=branch_id, session_id=session_id)
    report = data.get("report") or {}
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Metric", "Value"])
    for key, val in report.items():
        if isinstance(val, (dict, list)):
            continue
        writer.writerow([key, val])
    return buf.getvalue()


def export_report_pdf(*, branch_id, session_id) -> bytes:
    import html as html_module

    from apps.core.exports.pdf import render_pdf

    data = get_execution_report(branch_id=branch_id, session_id=session_id)
    report = data.get("report") or {}
    lines = ["<h1>Academic Year Promotion Report</h1>"]
    for key, val in report.items():
        if isinstance(val, (dict, list)):
            continue
        lines.append(
            f"<p><strong>{html_module.escape(str(key))}</strong>: "
            f"{html_module.escape(str(val))}</p>"
        )
    html = "\n".join(lines)
    return render_pdf(html)
