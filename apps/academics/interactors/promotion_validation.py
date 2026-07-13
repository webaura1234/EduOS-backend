"""Interactors — Promotion validation, Ready/Blocked, Execution Impact (Phase 2)."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.academics.interactors import promotion_preparation as prep_i
from apps.academics.models.promotion import ExecutionReadiness, PreparationStatus, PromotionAction
from apps.academics.queries import promotion as prom_q
from apps.academics.queries import promotion_preparation as prep_q
from apps.academics.queries import structure as struct_q
from apps.accounts.models.profile import AcademicStatus
from apps.admissions.queries import enrollment as enr_q
from apps.fees.enums import FeeStructureStatus
from apps.fees.queries import concession as conc_q
from apps.fees.queries import invoice as invoice_q
from apps.fees.queries import structure as fees_q

BLOCK_MISSING_FEE = "Missing Fee Structure"
BLOCK_DUPLICATE_ENROLLMENT = "Duplicate Enrollment"
BLOCK_MISSING_SECTION = "Missing Destination Section"
BLOCK_MISSING_CLASS = "Missing Destination Class"
BLOCK_MISSING_ENROLLMENT = "Missing Active Enrollment"
BLOCK_NOT_ACTIVE = "Student Transferred / Withdrawn"
BLOCK_MANUAL = "Manual Review Required"
BLOCK_PENDING = "Pending Prerequisites"
BLOCK_INVALID_BATCH = "Target Section Unavailable"

NON_EXECUTABLE = {
    PromotionAction.PENDING,
    PromotionAction.MANUAL_REVIEW,
}

OUTSTANDING_ISSUE_LIMIT = 50


def _format_inr(paise: int) -> str:
    rupees = paise / 100
    return f"₹{rupees:,.2f}"


def _outstanding_fees_message(count: int, total_paise: int) -> str:
    if count == 0:
        return ""
    amount = _format_inr(total_paise)
    noun = "student" if count == 1 else "students"
    verb = "owes" if count == 1 else "owe"
    return (
        f"{count} {noun} {verb} {amount} in the source year — "
        "balances will carry forward on promotion."
    )


def _resolve_fee_structure(branch_id, *, batch_id, academic_year_id):
    for s in fees_q.list_structures(branch_id, academic_year_id=academic_year_id):
        if s.batch_id == batch_id and s.status == FeeStructureStatus.PUBLISHED:
            return s
    return None


def _collect_outstanding_fee_issues(session, decisions) -> dict:
    issues: list[dict] = []
    total_paise = 0
    ready = [d for d in decisions if d.execution_readiness == ExecutionReadiness.READY]
    for d in ready:
        enr = enr_q.get_active_enrollment_for_profile(
            d.student_profile_id, academic_year_id=session.source_year_id
        )
        if not enr:
            continue
        balance = invoice_q.outstanding_balance_paise(enr.pk)
        if balance <= 0:
            continue
        total_paise += balance
        issues.append(
            {
                "studentName": d.student_name,
                "fromClassSection": _class_section_label(d.course_name, d.section_name),
                "outstandingPaise": balance,
                "decisionId": str(d.pk),
            }
        )
    issues.sort(key=lambda row: row["outstandingPaise"], reverse=True)
    return {
        "issues": issues[:OUTSTANDING_ISSUE_LIMIT],
        "totalPaise": total_paise,
        "count": len(issues),
    }


def _class_section_label(course_name: str, section: str) -> str:
    if course_name and section:
        return f"{course_name}-{section}"
    return course_name or section or "—"


def _validate_decision(session, decision, profile) -> tuple[str, list[str], dict]:
    """Return readiness, block_reasons, extra fields to save on decision."""
    reasons: list[str] = []
    fields: dict = {}
    action = decision.final_action

    if action in NON_EXECUTABLE:
        label = BLOCK_PENDING if action == PromotionAction.PENDING else BLOCK_MANUAL
        return ExecutionReadiness.BLOCKED, [label], fields

    if profile.academic_status != AcademicStatus.ACTIVE:
        return ExecutionReadiness.BLOCKED, [BLOCK_NOT_ACTIVE], fields

    enr = enr_q.get_active_enrollment_for_profile(
        profile.pk, academic_year_id=session.source_year_id
    )
    if not enr:
        return ExecutionReadiness.BLOCKED, [BLOCK_MISSING_ENROLLMENT], fields

    target_enr = enr_q.get_active_enrollment_for_profile(
        profile.pk, academic_year_id=session.target_year_id
    )
    if target_enr and action in (PromotionAction.PROMOTE, PromotionAction.RETAIN):
        return ExecutionReadiness.BLOCKED, [BLOCK_DUPLICATE_ENROLLMENT], fields

    if action in (PromotionAction.PROMOTE, PromotionAction.RETAIN):
        if not decision.target_course_id:
            return ExecutionReadiness.BLOCKED, [BLOCK_MISSING_CLASS], fields
        if not decision.target_batch_id:
            return ExecutionReadiness.BLOCKED, [BLOCK_MISSING_SECTION], fields
        batch = struct_q.get_batch(session.branch_id, decision.target_batch_id)
        if not batch or batch.academic_year_id != session.target_year_id:
            return ExecutionReadiness.BLOCKED, [BLOCK_INVALID_BATCH], fields

        fee = _resolve_fee_structure(
            session.branch_id,
            batch_id=decision.target_batch_id,
            academic_year_id=session.target_year_id,
        )
        if not fee:
            return ExecutionReadiness.BLOCKED, [BLOCK_MISSING_FEE], fields
        fields["target_fee_structure_id"] = fee.pk
        fields["target_fee_structure_name"] = fee.name

    return ExecutionReadiness.READY, reasons, fields


def _build_execution_impact(session, decisions, *, outstanding_detail=None) -> dict:
    ready = [d for d in decisions if d.execution_readiness == ExecutionReadiness.READY]
    blocked = [d for d in decisions if d.execution_readiness == ExecutionReadiness.BLOCKED]

    def count_action(action):
        return sum(1 for d in ready if d.final_action == action)

    new_enrollments = sum(
        1 for d in ready if d.final_action in (PromotionAction.PROMOTE, PromotionAction.RETAIN)
    )
    fee_assignments = sum(
        1
        for d in ready
        if d.final_action in (PromotionAction.PROMOTE, PromotionAction.RETAIN)
        and d.target_fee_structure_id
    )
    if outstanding_detail is None:
        outstanding_detail = _collect_outstanding_fee_issues(session, decisions)
    concessions = 0
    for d in ready:
        if conc_q.list_active_concessions_for_profile(
            branch_id=session.branch_id, profile_id=d.student_profile_id
        ).exists():
            concessions += 1

    manual = len(blocked) + sum(
        1 for d in ready if d.final_action in NON_EXECUTABLE
    )

    return {
        "newEnrollments": new_enrollments,
        "studentsPromoted": count_action(PromotionAction.PROMOTE),
        "studentsRetained": count_action(PromotionAction.RETAIN),
        "studentsGraduated": count_action(PromotionAction.GRADUATE),
        "studentsTransferOut": count_action(PromotionAction.TRANSFER_OUT),
        "studentsWithdrawn": count_action(PromotionAction.WITHDRAWN),
        "feeAssignmentsToBeCreated": fee_assignments,
        "outstandingBalancesToCarryForward": outstanding_detail["count"],
        "totalOutstandingPaise": outstanding_detail["totalPaise"],
        "studentsWithActiveConcessions": concessions,
        "studentsRequiringManualIntervention": manual,
    }


def _blocked_by_reason(decisions) -> dict[str, int]:
    counts: dict[str, int] = {}
    for d in decisions:
        if d.execution_readiness != ExecutionReadiness.BLOCKED:
            continue
        for r in d.block_reasons or []:
            counts[r] = counts.get(r, 0) + 1
    return counts


def _pick_samples(decisions, limit=8) -> list[dict]:
    samples: list[dict] = []
    seen_actions: set[str] = set()

    def add_sample(d):
        readiness = d.execution_readiness or ExecutionReadiness.BLOCKED
        samples.append(
            {
                "studentName": d.student_name,
                "fromClassSection": _class_section_label(d.course_name, d.section_name),
                "toClassSection": _class_section_label(d.target_course_name, d.target_section_name)
                if d.target_course_name or d.target_section_name
                else None,
                "finalAction": d.final_action,
                "feeStructureName": d.target_fee_structure_name or None,
                "executionReadiness": readiness,
                "statusLabel": "Ready" if readiness == ExecutionReadiness.READY else "Blocked",
                "blockReasons": d.block_reasons or [],
            }
        )

    for action in (PromotionAction.PROMOTE, PromotionAction.RETAIN, PromotionAction.GRADUATE):
        for d in decisions:
            if d.final_action == action and str(d.pk) not in seen_actions:
                add_sample(d)
                seen_actions.add(str(d.pk))
                break

    for d in decisions:
        if d.execution_readiness == ExecutionReadiness.BLOCKED and str(d.pk) not in seen_actions:
            add_sample(d)
            seen_actions.add(str(d.pk))
            break

    for d in decisions:
        if len(samples) >= limit:
            break
        if str(d.pk) in seen_actions:
            continue
        add_sample(d)
        seen_actions.add(str(d.pk))

    return samples[:limit]


def _module_checks() -> list[dict]:
    skipped = ["Transport", "Hostel", "Library", "Discipline", "ID Card"]
    return [
        {"id": m.lower().replace(" ", "_"), "label": m, "status": "skipped", "issueCount": 0}
        for m in skipped
    ]


@transaction.atomic
def run_validation(*, branch_id, session_id, user=None) -> dict:
    session = prep_q.require_approved_session(branch_id, session_id)
    if not session:
        from rest_framework.exceptions import ValidationError

        raise ValidationError({"sessionId": "Approved promotion session not found."})

    if session.preparation_status == PreparationStatus.LOCKED:
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("Unlock preparation before re-validating.")

    readiness_audit = prep_i.get_readiness_audit(branch_id=branch_id, session_id=session_id)
    session_blocking = not readiness_audit.get("canProceed")

    decisions = list(prep_q.list_decisions_with_profile(session.pk))
    for d in decisions:
        readiness, reasons, extra = _validate_decision(session, d, d.student_profile)
        prom_q.update_decision(
            d,
            {
                "execution_readiness": readiness,
                "block_reasons": reasons,
                **extra,
            },
            user=user,
        )

    decisions = list(prep_q.list_decisions_with_profile(session.pk))
    ready_count = sum(1 for d in decisions if d.execution_readiness == ExecutionReadiness.READY)
    blocked_count = sum(1 for d in decisions if d.execution_readiness == ExecutionReadiness.BLOCKED)

    fee_check_issues = sum(
        1 for d in decisions if BLOCK_MISSING_FEE in (d.block_reasons or [])
    )
    outstanding_detail = _collect_outstanding_fee_issues(session, decisions)
    execution_impact = _build_execution_impact(
        session, decisions, outstanding_detail=outstanding_detail
    )
    outstanding_count = outstanding_detail["count"]
    checks = [
        {
            "id": "promotion_decisions",
            "label": "Promotion Decisions",
            "status": "ready",
            "issueCount": 0,
        },
        {
            "id": "student_validation",
            "label": "Student Validation",
            "status": "blocking" if blocked_count else "ready",
            "issueCount": blocked_count,
        },
        {
            "id": "class_mapping",
            "label": "Class Mapping",
            "status": "ready",
            "issueCount": 0,
        },
        {
            "id": "section_mapping",
            "label": "Section Mapping",
            "status": "blocking"
            if any(BLOCK_MISSING_SECTION in (d.block_reasons or []) for d in decisions)
            else "ready",
            "issueCount": sum(
                1 for d in decisions if BLOCK_MISSING_SECTION in (d.block_reasons or [])
            ),
        },
        {
            "id": "fee_structures",
            "label": "Fee Structures",
            "status": "blocking" if fee_check_issues else "ready",
            "issueCount": fee_check_issues,
        },
        {
            "id": "outstanding_fees",
            "label": "Outstanding Fees",
            "status": "warning" if outstanding_count else "ready",
            "issueCount": outstanding_count,
            "message": _outstanding_fees_message(
                outstanding_count, outstanding_detail["totalPaise"]
            ),
            "issues": outstanding_detail["issues"],
            "totalOutstandingPaise": outstanding_detail["totalPaise"],
        },
    ]
    checks.extend(_module_checks())

    sample_students = _pick_samples(decisions)
    can_lock = not session_blocking and ready_count > 0 and blocked_count == 0

    validation_snapshot = {
        "validatedAt": timezone.now().isoformat(),
        "checks": checks,
        "students": {
            "ready": ready_count,
            "blocked": blocked_count,
            "blockedByReason": _blocked_by_reason(decisions),
        },
        "canLock": can_lock,
        "isStale": False,
    }
    preview_snapshot = {
        "executionImpact": execution_impact,
        "sampleStudents": sample_students,
        "students": validation_snapshot["students"],
    }

    prep_q.update_session(
        session,
        {
            "validation_snapshot": validation_snapshot,
            "execution_preview_snapshot": preview_snapshot,
            "preparation_status": PreparationStatus.IN_PROGRESS
            if session.preparation_status == PreparationStatus.NOT_STARTED
            else session.preparation_status,
        },
        user=user,
    )

    return {
        **validation_snapshot,
        "executionImpact": execution_impact,
        "sampleStudents": sample_students,
    }


def get_preview(*, branch_id, session_id) -> dict:
    from apps.academics.interactors import promotion_staleness as stale_i

    session = prep_q.require_approved_session(branch_id, session_id)
    if not session:
        from rest_framework.exceptions import ValidationError

        raise ValidationError({"sessionId": "Approved promotion session not found."})

    is_stale = False
    stale_changes: list[str] = []
    if session.preparation_status == PreparationStatus.LOCKED:
        is_stale, stale_changes = stale_i.check_and_apply_staleness(session)
        session.refresh_from_db()

    preview = session.execution_preview_snapshot or {}
    validation = session.validation_snapshot or {}
    return {
        "executionImpact": preview.get("executionImpact"),
        "sampleStudents": preview.get("sampleStudents", []),
        "students": validation.get("students") or preview.get("students"),
        "checks": validation.get("checks", []),
        "canLock": validation.get("canLock", False),
        "isStale": is_stale or session.preparation_status == PreparationStatus.INVALID,
        "staleChanges": stale_changes,
        "preparationStatus": session.preparation_status,
    }


def list_blocked_students(*, branch_id, session_id, page=1, page_size=50) -> dict:
    session = prep_q.require_approved_session(branch_id, session_id)
    if not session:
        from rest_framework.exceptions import ValidationError

        raise ValidationError({"sessionId": "Approved promotion session not found."})

    rows, total = prep_q.list_blocked_decisions(session.pk, page=page, page_size=page_size)
    items = [
        {
            "decisionId": str(d.pk),
            "studentName": d.student_name,
            "fromClassSection": _class_section_label(d.course_name, d.section_name),
            "finalAction": d.final_action,
            "blockReasons": d.block_reasons or [],
        }
        for d in rows
    ]
    return {"students": items, "total": total, "page": page, "pageSize": page_size}
