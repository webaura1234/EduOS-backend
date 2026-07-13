"""Interactors — Academic year promotion workspace (Phase 1, decisions only)."""

from __future__ import annotations

from django.db import transaction
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.academics.interactors import calendar as cal_i
from apps.academics.interactors import promotion_recommendations as rec_i
from apps.academics.models.promotion import (
    AcademicPromotionDecision,
    PromotionAction,
    PromotionExecutionStatus,
    PromotionSessionStatus,
)
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import promotion as prom_q
from apps.academics.queries import rollover as rol_q
from apps.analytics.interactors import audit as audit_i


def _session_is_editable(session) -> bool:
    return session.status == PromotionSessionStatus.DRAFT


def _require_editable(session) -> None:
    if not _session_is_editable(session):
        raise PermissionDenied("Promotion decisions are approved and cannot be modified.")


def _decision_to_dict(d: AcademicPromotionDecision) -> dict:
    return {
        "id": str(d.pk),
        "studentId": str(d.student_profile.user_id),
        "studentName": d.student_name,
        "courseId": str(d.course_id) if d.course_id else None,
        "courseName": d.course_name,
        "batchId": str(d.batch_id) if d.batch_id else None,
        "sectionName": d.section_name,
        "branchId": str(d.branch_id_snapshot),
        "recommendedAction": d.recommended_action,
        "finalAction": d.final_action,
        "reasonLabel": d.recommended_reason_label or None,
        "isOverridden": d.is_overridden,
        "overrideReason": d.override_reason or None,
    }


def _counts_to_dict(counts: dict) -> dict:
    return {
        "total": counts.get("total", 0),
        "promote": counts.get(PromotionAction.PROMOTE, 0),
        "retain": counts.get(PromotionAction.RETAIN, 0),
        "graduate": counts.get(PromotionAction.GRADUATE, 0),
        "manualReview": counts.get(PromotionAction.MANUAL_REVIEW, 0),
        "pending": counts.get(PromotionAction.PENDING, 0),
        "transferOut": counts.get(PromotionAction.TRANSFER_OUT, 0),
        "withdrawn": counts.get(PromotionAction.WITHDRAWN, 0),
    }


def _session_to_dict(session, *, counts: dict | None = None) -> dict:
    payload = {
        "id": str(session.pk),
        "status": session.status,
        "sourceYearId": str(session.source_year_id),
        "sourceYearLabel": session.source_year.name,
        "targetYearId": str(session.target_year_id),
        "targetYearLabel": session.target_year.name,
        "branchId": str(session.branch_id),
        "approvedAt": session.approved_at.isoformat() if session.approved_at else None,
        "preparationStatus": getattr(session, "preparation_status", None),
    }
    if counts is not None:
        payload["counts"] = _counts_to_dict(counts)
    return payload


def build_decisions(*, session, tenant, user=None) -> int:
    """Analyze ACTIVE students and create/replace decision rows."""
    prom_q.delete_decisions_for_session(session.pk)
    enrollments = rol_q.list_enrollments_in_year(session.branch_id, session.source_year_id)
    rows: list[AcademicPromotionDecision] = []
    for enrollment in enrollments:
        profile = enrollment.student_profile
        rec = rec_i.recommend_for_student(
            profile=profile,
            tenant=tenant,
            source_year_id=session.source_year_id,
            enrollment=enrollment,
        )
        batch = enrollment.batch
        rows.append(
            AcademicPromotionDecision(
                session=session,
                student_profile=profile,
                student_name=profile.user.full_name,
                branch_id_snapshot=session.branch_id,
                course_id=batch.course_id if batch else None,
                course_name=batch.course.name if batch else "",
                batch_id=batch.pk if batch else None,
                section_name=batch.name if batch else "",
                recommended_action=rec.action,
                recommended_reason_code=rec.reason_code,
                recommended_reason_label=rec.reason_label,
                final_action=rec.action,
                is_overridden=False,
                override_reason="",
                created_by=user,
                updated_by=user,
            )
        )
    if rows:
        prom_q.bulk_create_decisions(rows)
    return len(rows)


def get_current_state(*, branch_id, tenant) -> dict:
    current_year = cal_q.get_current_year(branch_id)
    if not current_year:
        return {"status": "none", "sourceYearLabel": None, "targetYearLabel": None}

    draft = prom_q.get_draft_session(branch_id, current_year.pk)
    if draft:
        counts = prom_q.count_by_final_action(draft.pk)
        return {
            "status": "draft",
            "session": _session_to_dict(draft, counts=counts),
            "sourceYearLabel": draft.source_year.name,
            "targetYearLabel": draft.target_year.name,
        }

    approved = prom_q.get_approved_session(branch_id, current_year.pk)
    if approved:
        counts = prom_q.count_by_final_action(approved.pk)
        from apps.academics.models.promotion import PreparationStatus
        from apps.academics.queries import promotion_preparation as prep_q2

        readiness = prep_q2.count_readiness(approved.pk)
        payload = {
            "status": "approved",
            "session": _session_to_dict(approved, counts=counts),
            "sourceYearLabel": approved.source_year.name,
            "targetYearLabel": approved.target_year.name,
            "preparationStatus": approved.preparation_status,
            "readyCount": readiness.get("ready", 0),
            "blockedCount": readiness.get("blocked", 0),
            "isStale": approved.preparation_status == PreparationStatus.INVALID,
            "isReadyForExecution": (
                approved.preparation_status == PreparationStatus.LOCKED
                and approved.preparation_status != PreparationStatus.INVALID
                and readiness.get("ready", 0) > 0
            ),
            "canBeginPreparation": approved.preparation_status == PreparationStatus.NOT_STARTED,
            "canContinuePreparation": approved.preparation_status
            in (PreparationStatus.IN_PROGRESS, PreparationStatus.INVALID),
        }
        if approved.preparation_status == PreparationStatus.LOCKED:
            from apps.academics.interactors import promotion_staleness as stale_i

            is_stale, _ = stale_i.check_and_apply_staleness(approved)
            if is_stale:
                approved.refresh_from_db()
                payload["isStale"] = True
                payload["preparationStatus"] = approved.preparation_status
                payload["isReadyForExecution"] = False

        from apps.academics.models.promotion import PromotionExecutionStatus
        from apps.academics.queries import promotion_execution as exec_q2

        payload["executionStatus"] = approved.execution_status
        payload["executedAt"] = approved.executed_at.isoformat() if approved.executed_at else None
        payload["canExecute"] = (
            approved.preparation_status == PreparationStatus.LOCKED
            and not payload.get("isStale", False)
            and approved.execution_status
            not in (PromotionExecutionStatus.SUCCEEDED, PromotionExecutionStatus.RUNNING)
            and readiness.get("ready", 0) > 0
            and readiness.get("blocked", 0) == 0
        )
        payload["isExecutionRunning"] = approved.execution_status == PromotionExecutionStatus.RUNNING
        payload["canReopenReview"] = approved.execution_status == PromotionExecutionStatus.NOT_STARTED
        if approved.execution_report:
            payload["executionSummary"] = approved.execution_report
        latest_run = exec_q2.get_latest_run(approved.pk)
        if latest_run:
            payload["executionRunId"] = str(latest_run.pk)
        return payload

    return {
        "status": "none",
        "sourceYearLabel": current_year.name,
        "targetYearLabel": None,
        "currentYearId": str(current_year.pk),
    }


@transaction.atomic
def start_promotion(
    *,
    branch,
    tenant,
    source_year_id,
    target_year_id=None,
    target_year_create=None,
    user=None,
) -> dict:
    source_year = cal_q.get_year(branch.pk, source_year_id)
    if not source_year:
        raise ValidationError({"sourceYearId": "Source academic year not found."})

    existing_draft = prom_q.get_draft_session(branch.pk, source_year.pk)
    if existing_draft:
        raise ValidationError({"detail": "A promotion review is already in progress."})

    approved = prom_q.get_approved_session(branch.pk, source_year.pk)
    if approved:
        raise PermissionDenied("Promotion decisions for this year are already approved.")

    if target_year_id:
        target_year = cal_q.get_year(branch.pk, target_year_id)
        if not target_year:
            raise ValidationError({"targetYearId": "Target academic year not found."})
    elif target_year_create:
        data = target_year_create
        target_year = cal_i.create_academic_year(
            branch.pk,
            name=data["name"],
            start_date=data["startDate"],
            end_date=data["endDate"],
            is_current=False,
            user=user,
        )
    else:
        raise ValidationError({"targetYearId": "Target academic year is required."})

    if target_year.pk == source_year.pk:
        raise ValidationError({"targetYearId": "Target year must differ from source year."})

    session = prom_q.create_session(
        branch=branch,
        source_year=source_year,
        target_year=target_year,
        user=user,
    )
    student_count = build_decisions(session=session, tenant=tenant, user=user)
    counts = prom_q.count_by_final_action(session.pk)
    return {
        "session": _session_to_dict(session, counts=counts),
        "studentsAnalyzed": student_count,
    }


def get_session_detail(*, branch_id, session_id) -> dict:
    session = prom_q.get_session(branch_id, session_id)
    if not session:
        raise ValidationError({"sessionId": "Promotion session not found."})
    counts = prom_q.count_by_final_action(session.pk)
    return _session_to_dict(session, counts=counts)


def list_session_decisions(
    *,
    branch_id,
    session_id,
    branch_filter=None,
    course_id=None,
    batch_id=None,
    action=None,
    page=1,
    page_size=50,
) -> dict:
    session = prom_q.get_session(branch_id, session_id)
    if not session:
        raise ValidationError({"sessionId": "Promotion session not found."})

    qs = prom_q.list_decisions(
        session.pk,
        branch_id=branch_filter,
        course_id=course_id,
        batch_id=batch_id,
        action=action,
    )
    total = qs.count()
    offset = (max(page, 1) - 1) * page_size
    items = [_decision_to_dict(d) for d in qs[offset : offset + page_size]]
    return {"decisions": items, "total": total, "page": page, "pageSize": page_size}


@transaction.atomic
def override_decision(
    *,
    branch_id,
    session_id,
    decision_id,
    final_action: str,
    reason: str,
    user=None,
    request=None,
) -> dict:
    session = prom_q.get_session(branch_id, session_id)
    if not session:
        raise ValidationError({"sessionId": "Promotion session not found."})
    _require_editable(session)

    if not reason or len(reason.strip()) < 10:
        raise ValidationError({"reason": "A reason of at least 10 characters is required."})

    valid_actions = {a.value for a in PromotionAction}
    if final_action not in valid_actions:
        raise ValidationError({"finalAction": "Invalid action."})

    decision = prom_q.get_decision(session.pk, decision_id)
    if not decision:
        raise ValidationError({"decisionId": "Decision not found."})

    from_action = decision.final_action
    prom_q.create_override_log(
        session=session,
        decision=decision,
        actor=user,
        from_action=from_action,
        to_action=final_action,
        reason=reason.strip(),
    )
    prom_q.update_decision(
        decision,
        {
            "final_action": final_action,
            "is_overridden": True,
            "override_reason": reason.strip(),
        },
        user=user,
    )

    if user and request is not None:
        audit_i.record_audit(
            tenant=user.tenant,
            actor=user,
            action="promotion.decision.override",
            entity_type="promotion_decision",
            entity_id=str(decision.pk),
            diff={
                "fromAction": from_action,
                "toAction": final_action,
                "reason": reason.strip(),
                "reasonCode": decision.recommended_reason_code,
            },
            request=request,
        )

    return _decision_to_dict(decision)


@transaction.atomic
def bulk_override_decisions(
    *,
    branch_id,
    session_id,
    final_action: str,
    reason: str,
    decision_ids: list | None = None,
    filter_action: str | None = None,
    course_id=None,
    batch_id=None,
    user=None,
    request=None,
) -> dict:
    """
    Apply the same override to many decisions at once.

    Selection is either an explicit list of ``decision_ids`` or a filter
    (``filter_action`` / ``course_id`` / ``batch_id``). Exactly one selection
    mode must be provided. Returns the number of decisions updated plus the
    refreshed category counts so the UI can re-render without a second call.
    """
    session = prom_q.get_session(branch_id, session_id)
    if not session:
        raise ValidationError({"sessionId": "Promotion session not found."})
    _require_editable(session)

    if not reason or len(reason.strip()) < 10:
        raise ValidationError({"reason": "A reason of at least 10 characters is required."})

    valid_actions = {a.value for a in PromotionAction}
    if final_action not in valid_actions:
        raise ValidationError({"finalAction": "Invalid action."})

    reason = reason.strip()

    if decision_ids:
        qs = prom_q.list_decisions(session.pk).filter(pk__in=decision_ids)
    elif filter_action or course_id or batch_id:
        qs = prom_q.list_decisions(
            session.pk,
            course_id=course_id,
            batch_id=batch_id,
            action=filter_action,
        )
    else:
        raise ValidationError(
            {"decisionIds": "Provide decisionIds or a filter (action/course/batch)."}
        )

    decisions = list(qs)
    if not decisions:
        raise ValidationError({"decisionIds": "No matching decisions to override."})

    updated = 0
    for decision in decisions:
        from_action = decision.final_action
        if from_action == final_action and decision.is_overridden:
            continue
        prom_q.create_override_log(
            session=session,
            decision=decision,
            actor=user,
            from_action=from_action,
            to_action=final_action,
            reason=reason,
        )
        prom_q.update_decision(
            decision,
            {
                "final_action": final_action,
                "is_overridden": True,
                "override_reason": reason,
            },
            user=user,
        )
        updated += 1

    if user and request is not None and updated:
        audit_i.record_audit(
            tenant=user.tenant,
            actor=user,
            action="promotion.decision.bulk_override",
            entity_type="promotion_session",
            entity_id=str(session.pk),
            diff={
                "toAction": final_action,
                "reason": reason,
                "updatedCount": updated,
                "selection": (
                    {"decisionIds": [str(d) for d in decision_ids]}
                    if decision_ids
                    else {
                        "action": filter_action,
                        "courseId": str(course_id) if course_id else None,
                        "batchId": str(batch_id) if batch_id else None,
                    }
                ),
            },
            request=request,
        )

    return {
        "updated": updated,
        "counts": _counts_to_dict(prom_q.count_by_final_action(session.pk)),
    }


@transaction.atomic
def approve_promotion(*, branch_id, session_id, user=None, request=None) -> dict:
    session = prom_q.get_session(branch_id, session_id)
    if not session:
        raise ValidationError({"sessionId": "Promotion session not found."})

    if session.status == PromotionSessionStatus.APPROVED:
        raise ValidationError({"detail": "Promotion decisions are already approved."})

    _require_editable(session)
    counts = prom_q.count_by_final_action(session.pk)
    unresolved = counts.get(PromotionAction.PENDING, 0) + counts.get(PromotionAction.MANUAL_REVIEW, 0)
    if unresolved:
        raise ValidationError(
            {
                "detail": (
                    f"Resolve all pending and manual-review decisions before approving "
                    f"({unresolved} remaining)."
                ),
            }
        )
    prom_q.approve_session(session, user=user)
    counts = prom_q.count_by_final_action(session.pk)
    decisions = [_decision_to_dict(d) for d in prom_q.list_all_decisions(session.pk)]

    if user and request is not None:
        audit_i.record_audit(
            tenant=user.tenant,
            actor=user,
            action="promotion.decisions.approve",
            entity_type="promotion_session",
            entity_id=str(session.pk),
            diff={"counts": _counts_to_dict(counts)},
            request=request,
        )

    return {
        "session": _session_to_dict(session, counts=counts),
        "decisions": decisions,
        "message": "Review complete",
    }


@transaction.atomic
def reopen_promotion_review(
    *,
    branch_id,
    session_id,
    reason: str,
    user=None,
    request=None,
) -> dict:
    """Revert an approved session to draft so admins can override decisions."""
    session = prom_q.get_session(branch_id, session_id)
    if not session:
        raise ValidationError({"sessionId": "Promotion session not found."})

    if session.status != PromotionSessionStatus.APPROVED:
        raise ValidationError({"detail": "Only approved promotion sessions can be reopened for review."})

    if session.execution_status != PromotionExecutionStatus.NOT_STARTED:
        raise PermissionDenied(
            "Cannot reopen review after promotion execution has started or completed."
        )

    if not reason or len(reason.strip()) < 10:
        raise ValidationError({"reason": "A reason of at least 10 characters is required."})

    prom_q.clear_decision_validation_state(session.pk)
    prom_q.reopen_session(session, user=user)
    session.refresh_from_db()

    if user and request is not None:
        audit_i.record_audit(
            tenant=user.tenant,
            actor=user,
            action="promotion.review.reopen",
            entity_type="promotion_session",
            entity_id=str(session.pk),
            diff={"reason": reason.strip()},
            request=request,
        )

    counts = prom_q.count_by_final_action(session.pk)
    return {
        "session": _session_to_dict(session, counts=counts),
        "message": "Review reopened",
    }
