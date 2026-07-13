"""Interactors — Promotion preparation: mappings, lock/unlock (Phase 2)."""

from __future__ import annotations

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.academics.interactors import promotion_staleness as stale_i
from apps.academics.interactors.promotion_recommendations import get_next_course
from apps.academics.models import Course
from apps.academics.models.promotion import (
    PreparationLogEvent,
    PreparationStatus,
    PromotionAction,
)
from apps.academics.queries import promotion as prom_q
from apps.academics.queries import promotion_preparation as prep_q
from apps.academics.queries import rollover as rol_q
from apps.academics.queries import structure as struct_q
from apps.academics.models.rollover import RolloverRunStatus
from apps.analytics.interactors import audit as audit_i


def _require_approved(branch_id, session_id):
    session = prep_q.require_approved_session(branch_id, session_id)
    if not session:
        raise ValidationError({"sessionId": "Approved promotion session not found."})
    return session


def _class_section_label(course_name: str, section: str) -> str:
    if course_name and section:
        return f"{course_name}-{section}"
    return course_name or section or "—"


def _find_target_batch(branch_id, *, course_id, academic_year_id, section_name):
    batches = struct_q.list_batches(
        branch_id, course_id=course_id, academic_year_id=academic_year_id
    )
    for b in batches:
        if b.name == section_name:
            return b
    return batches.first() if batches.exists() else None


def _source_batch_defaults(branch_id, *, course_id, academic_year_id, section_name):
    """Capacity and class teacher copied from the matching source-year section."""
    for batch in struct_q.list_batches(
        branch_id, course_id=course_id, academic_year_id=academic_year_id
    ):
        if batch.name == section_name:
            return batch.capacity, batch.class_teacher_id
    return 40, None


def _provision_target_batches(session, user=None) -> None:
    """
    Ensure target-year sections exist for every promote/retain decision.

    Without this, class mapping shows "0 sections" because batches only exist
    in the source academic year until rollover/promotion execution runs.
    """
    branch_id = session.branch_id
    mappings = {
        str(m.source_course_id): m for m in prep_q.list_class_mappings(session.pk)
    }
    # (target_course_id, section_name) -> defaults
    needed: dict[tuple, dict] = {}

    for d in prom_q.list_all_decisions(session.pk):
        if d.final_action not in (PromotionAction.PROMOTE, PromotionAction.RETAIN):
            continue
        if not d.course_id or not d.section_name:
            continue

        if d.final_action == PromotionAction.PROMOTE:
            mapping = mappings.get(str(d.course_id))
            if not mapping:
                continue
            target_course_id = mapping.target_course_id
        else:
            target_course_id = d.course_id

        key = (target_course_id, d.section_name)
        if key in needed:
            continue
        capacity, class_teacher_id = _source_batch_defaults(
            branch_id,
            course_id=d.course_id,
            academic_year_id=session.source_year_id,
            section_name=d.section_name,
        )
        needed[key] = {"capacity": capacity, "class_teacher_id": class_teacher_id}

    for (target_course_id, section_name), defaults in needed.items():
        exists = (
            struct_q.list_batches(
                branch_id,
                course_id=target_course_id,
                academic_year_id=session.target_year_id,
            )
            .filter(name=section_name)
            .exists()
        )
        if exists:
            continue
        try:
            course = Course.objects.get(pk=target_course_id)
        except Course.DoesNotExist:
            continue
        struct_q.create_batch(
            course=course,
            academic_year=session.target_year,
            name=section_name,
            capacity=defaults["capacity"],
            class_teacher_id=defaults["class_teacher_id"],
            user=user,
        )


def _seed_class_mappings(session, user=None):
    decisions = prom_q.list_all_decisions(session.pk)
    source_courses: dict = {}
    for d in decisions:
        if d.final_action != PromotionAction.PROMOTE or not d.course_id:
            continue
        if d.course_id not in source_courses:
            source_courses[d.course_id] = d.course_name

    rows = []
    for course_id, course_name in source_courses.items():
        try:
            course = Course.objects.select_related("department").get(pk=course_id)
        except Course.DoesNotExist:
            continue
        next_c = get_next_course(course.department_id, course_id)
        if not next_c:
            continue
        rows.append(
            {
                "source_course_id": course_id,
                "source_course_name": course_name,
                "target_course_id": next_c.pk,
                "target_course_name": next_c.name,
            }
        )
    if rows:
        prep_q.bulk_upsert_class_mappings(session.pk, rows, user=user)


def _apply_destinations_from_mappings(session, user=None):
    mappings = {
        str(m.source_course_id): m for m in prep_q.list_class_mappings(session.pk)
    }
    for d in prep_q.list_decisions_with_profile(session.pk):
        action = d.final_action
        fields = {}

        if action == PromotionAction.PROMOTE and d.course_id:
            m = mappings.get(str(d.course_id))
            if m:
                fields["target_course_id"] = m.target_course_id
                fields["target_course_name"] = m.target_course_name
                batch = _find_target_batch(
                    session.branch_id,
                    course_id=m.target_course_id,
                    academic_year_id=session.target_year_id,
                    section_name=d.section_name,
                )
                if batch:
                    fields["target_batch_id"] = batch.pk
                    fields["target_section_name"] = batch.name
                else:
                    fields["target_batch_id"] = None
                    fields["target_section_name"] = ""

        elif action == PromotionAction.RETAIN and d.course_id:
            fields["target_course_id"] = d.course_id
            fields["target_course_name"] = d.course_name
            batch = _find_target_batch(
                session.branch_id,
                course_id=d.course_id,
                academic_year_id=session.target_year_id,
                section_name=d.section_name,
            )
            if batch:
                fields["target_batch_id"] = batch.pk
                fields["target_section_name"] = batch.name

        elif action in (
            PromotionAction.GRADUATE,
            PromotionAction.TRANSFER_OUT,
            PromotionAction.WITHDRAWN,
        ):
            fields["target_course_id"] = None
            fields["target_course_name"] = ""
            fields["target_batch_id"] = None
            fields["target_section_name"] = ""

        if fields:
            prom_q.update_decision(d, fields, user=user)


def get_readiness_audit(*, branch_id, session_id) -> dict:
    session = _require_approved(branch_id, session_id)
    checks = []
    current = session.source_year
    target = session.target_year

    def add(check_id, label, status, message=""):
        checks.append({"id": check_id, "label": label, "status": status, "message": message})

    add("source_year", "Source Academic Year", "ready" if current and current.is_active else "blocking")
    add("target_year", "Target Academic Year", "ready" if target and target.is_active else "blocking")
    add("decisions_approved", "Promotion Decisions", "ready")

    if current and not current.is_current:
        add("source_current", "Current Academic Year", "blocking", "Source year is not the current year.")
    elif current and current.is_frozen:
        add("source_current", "Current Academic Year", "warning", "Source year is frozen.")

    run = rol_q.get_latest_rollover_run(branch_id)
    if (
        run
        and run.status == RolloverRunStatus.SUCCEEDED
        and run.from_year_id == session.source_year_id
        and run.to_year_id == session.target_year_id
    ):
        add("not_executed", "Not Already Executed", "blocking", "Promotion was already executed via rollover.")

    blocking = sum(1 for c in checks if c["status"] == "blocking")
    return {
        "checks": checks,
        "canProceed": blocking == 0,
    }


def get_preparation_state(*, branch_id, session_id) -> dict:
    from apps.academics.interactors import promotion_validation as val_i

    session = _require_approved(branch_id, session_id)
    is_stale = False
    stale_changes: list[str] = []
    if session.preparation_status == PreparationStatus.LOCKED:
        is_stale, stale_changes = stale_i.check_and_apply_staleness(session)
        session.refresh_from_db()

    readiness = prep_q.count_readiness(session.pk)
    snapshot = session.validation_snapshot or {}
    preview = session.execution_preview_snapshot or {}

    return {
        "sessionId": str(session.pk),
        "preparationStatus": session.preparation_status,
        "isStale": is_stale or session.preparation_status == PreparationStatus.INVALID,
        "staleChanges": stale_changes,
        "sourceYearLabel": session.source_year.name,
        "targetYearLabel": session.target_year.name,
        "students": readiness,
        "executionImpact": preview.get("executionImpact"),
        "canLock": snapshot.get("canLock", False),
        "isReadyForExecution": (
            session.preparation_status == PreparationStatus.LOCKED
            and not is_stale
            and readiness.get("ready", 0) > 0
            and readiness.get("blocked", 0) == 0
        ),
        "mappingsEditable": prep_q.preparation_mappings_editable(session),
        "executionStatus": session.execution_status,
    }


@transaction.atomic
def start_preparation(*, branch_id, session_id, user=None) -> dict:
    session = _require_approved(branch_id, session_id)
    if session.preparation_status == PreparationStatus.LOCKED:
        raise PermissionDenied("Preparation is locked. Unlock before making changes.")

    if session.preparation_status == PreparationStatus.NOT_STARTED:
        prep_q.update_session(
            session,
            {
                "preparation_status": PreparationStatus.IN_PROGRESS,
                "preparation_started_at": timezone.now(),
            },
            user=user,
        )

    _seed_class_mappings(session, user=user)
    _provision_target_batches(session, user=user)
    _apply_destinations_from_mappings(session, user=user)
    session.refresh_from_db()
    return get_preparation_state(branch_id=branch_id, session_id=session_id)


def list_class_mappings(*, branch_id, session_id) -> dict:
    session = _require_approved(branch_id, session_id)
    if prep_q.preparation_mappings_editable(session):
        needs_batches = prom_q.list_decisions(session.pk).filter(
            final_action__in=[PromotionAction.PROMOTE, PromotionAction.RETAIN],
            target_batch_id__isnull=True,
        ).exists()
        if needs_batches:
            _provision_target_batches(session)
            _apply_destinations_from_mappings(session)
    rows = []
    for m in prep_q.list_class_mappings(session.pk):
        target_batches = struct_q.list_batches(
            branch_id, course_id=m.target_course_id, academic_year_id=session.target_year_id
        )
        rows.append(
            {
                "sourceCourseId": str(m.source_course_id),
                "sourceCourseName": m.source_course_name,
                "targetCourseId": str(m.target_course_id),
                "targetCourseName": m.target_course_name,
                "targetBatchCount": target_batches.count(),
                "targetSections": list(target_batches.values_list("name", flat=True)),
            }
        )
    return {"mappings": rows, "mappingsEditable": prep_q.preparation_mappings_editable(session)}


@transaction.atomic
def update_class_mappings(*, branch_id, session_id, mappings: list[dict], user=None) -> dict:
    session = _require_approved(branch_id, session_id)
    if not prep_q.preparation_mappings_editable(session):
        raise PermissionDenied("Class mappings cannot be changed while preparation is locked.")

    rows = []
    for item in mappings:
        source_id = item.get("sourceCourseId")
        target_id = item.get("targetCourseId")
        if not source_id or not target_id:
            continue
        try:
            target = Course.objects.get(pk=target_id)
        except Course.DoesNotExist:
            raise ValidationError({"targetCourseId": "Destination class not found."})
        source_name = item.get("sourceCourseName", "")
        rows.append(
            {
                "source_course_id": source_id,
                "source_course_name": source_name,
                "target_course_id": target_id,
                "target_course_name": target.name,
            }
        )
    prep_q.bulk_upsert_class_mappings(session.pk, rows, user=user)
    _provision_target_batches(session, user=user)
    _apply_destinations_from_mappings(session, user=user)
    return list_class_mappings(branch_id=branch_id, session_id=session_id)


def list_section_mappings(
    *, branch_id, session_id, course_id=None, page=1, page_size=50
) -> dict:
    session = _require_approved(branch_id, session_id)
    qs = prep_q.list_decisions_with_profile(session.pk)
    if course_id:
        qs = qs.filter(course_id=course_id)
    qs = qs.filter(
        final_action__in=[PromotionAction.PROMOTE, PromotionAction.RETAIN]
    )
    total = qs.count()
    offset = (max(page, 1) - 1) * page_size
    items = []
    batch_strength: dict = {}

    for d in qs[offset : offset + page_size]:
        dest_batch = None
        capacity = None
        strength = None
        if d.target_batch_id:
            dest_batch = struct_q.get_batch(branch_id, d.target_batch_id)
            if dest_batch:
                capacity = dest_batch.capacity
                bid = str(dest_batch.pk)
                if bid not in batch_strength:
                    from apps.admissions.queries import enrollment as enr_q

                    batch_strength[bid] = enr_q.enrollments_in_batch(dest_batch.pk).count()
                strength = batch_strength.get(str(dest_batch.pk), 0)

        items.append(
            {
                "decisionId": str(d.pk),
                "studentName": d.student_name,
                "fromClassSection": _class_section_label(d.course_name, d.section_name),
                "toClassSection": _class_section_label(d.target_course_name, d.target_section_name),
                "finalAction": d.final_action,
                "targetBatchId": str(d.target_batch_id) if d.target_batch_id else None,
                "sectionStrength": strength,
                "capacity": capacity,
                "availableSeats": (capacity - strength) if capacity is not None and strength is not None else None,
            }
        )
    return {
        "rows": items,
        "total": total,
        "page": page,
        "pageSize": page_size,
        "mappingsEditable": prep_q.preparation_mappings_editable(session),
    }


@transaction.atomic
def update_section_mappings(*, branch_id, session_id, assignments: list[dict], user=None) -> dict:
    session = _require_approved(branch_id, session_id)
    if not prep_q.preparation_mappings_editable(session):
        raise PermissionDenied("Section mappings cannot be changed while preparation is locked.")

    for item in assignments:
        decision_id = item.get("decisionId")
        batch_id = item.get("targetBatchId")
        decision = prom_q.get_decision(session.pk, decision_id)
        if not decision:
            continue
        batch = struct_q.get_batch(branch_id, batch_id) if batch_id else None
        if batch_id and not batch:
            raise ValidationError({"targetBatchId": "Destination section not found."})
        if batch and batch.academic_year_id != session.target_year_id:
            raise ValidationError({"targetBatchId": "Section must belong to the target academic year."})
        prom_q.update_decision(
            decision,
            {
                "target_batch_id": batch.pk if batch else None,
                "target_section_name": batch.name if batch else "",
                "target_course_id": batch.course_id if batch else decision.target_course_id,
                "target_course_name": batch.course.name if batch else decision.target_course_name,
            },
            user=user,
        )
    return {"updated": len(assignments)}


@transaction.atomic
def lock_preparation(*, branch_id, session_id, user=None, request=None) -> dict:
    from apps.academics.interactors import promotion_validation as val_i

    session = _require_approved(branch_id, session_id)
    if session.preparation_status == PreparationStatus.LOCKED:
        raise ValidationError({"detail": "Preparation is already locked."})

    result = val_i.run_validation(branch_id=branch_id, session_id=session_id, user=user)
    blocked = (result.get("students") or {}).get("blocked", 0)
    if blocked:
        raise ValidationError(
            {
                "detail": (
                    f"Resolve all blocked students before locking preparation ({blocked} blocked)."
                ),
            }
        )
    if not result.get("canLock"):
        raise ValidationError({"detail": "Resolve blocking issues before locking preparation."})

    fingerprint = stale_i.build_fingerprint(session)
    from apps.academics.interactors import promotion_execution as exec_i

    exec_i.refresh_execution_confirm_token(session, fingerprint, user=user)
    session.refresh_from_db()
    prep_q.update_session(
        session,
        {
            "preparation_status": PreparationStatus.LOCKED,
            "preparation_locked_at": timezone.now(),
            "preparation_locked_by": user,
            "lock_fingerprint": fingerprint,
            "staleness_detected_at": None,
        },
        user=user,
    )
    prep_q.create_preparation_log(
        session=session,
        event=PreparationLogEvent.LOCK,
        actor=user,
        details={"ready": result.get("students", {}).get("ready", 0)},
    )
    if user and request:
        audit_i.record_audit(
            tenant=user.tenant,
            actor=user,
            action="promotion.preparation.lock",
            entity_type="promotion_session",
            entity_id=str(session.pk),
            diff={"ready": result.get("students", {}).get("ready", 0)},
            request=request,
        )
    session.refresh_from_db()
    return get_preparation_state(branch_id=branch_id, session_id=session_id)


@transaction.atomic
def unlock_preparation(*, branch_id, session_id, reason: str, user=None, request=None) -> dict:
    session = _require_approved(branch_id, session_id)
    from apps.academics.models.promotion import PromotionExecutionStatus

    if session.execution_status != PromotionExecutionStatus.NOT_STARTED:
        raise PermissionDenied(
            "Cannot unlock preparation after promotion execution has started or completed."
        )
    if session.preparation_status not in (PreparationStatus.LOCKED, PreparationStatus.INVALID):
        raise ValidationError({"detail": "Preparation is not locked."})
    if not reason or len(reason.strip()) < 10:
        raise ValidationError({"reason": "A reason of at least 10 characters is required."})

    prep_q.update_session(
        session,
        {
            "preparation_status": PreparationStatus.IN_PROGRESS,
            "preparation_locked_at": None,
            "preparation_locked_by": None,
            "lock_fingerprint": {},
            "staleness_detected_at": None,
        },
        user=user,
    )
    prep_q.create_preparation_log(
        session=session,
        event=PreparationLogEvent.UNLOCK,
        actor=user,
        reason=reason.strip(),
    )
    if user and request:
        audit_i.record_audit(
            tenant=user.tenant,
            actor=user,
            action="promotion.preparation.unlock",
            entity_type="promotion_session",
            entity_id=str(session.pk),
            diff={"reason": reason.strip()},
            request=request,
        )
    return get_preparation_state(branch_id=branch_id, session_id=session_id)
