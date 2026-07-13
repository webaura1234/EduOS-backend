"""Build and compare lock fingerprints for promotion preparation staleness."""

from __future__ import annotations

from apps.academics.models import AcademicYear, Batch, Course
from apps.academics.models.promotion import PreparationLogEvent, PreparationStatus
from apps.academics.queries import promotion_preparation as prep_q
from apps.accounts.models.profile import StudentProfile
from apps.admissions.models import StudentEnrollment
from apps.fees.models import FeeStructure


def _year_fp(year: AcademicYear | None) -> dict | None:
    if not year:
        return None
    return {
        "id": str(year.pk),
        "version": year.version,
        "isCurrent": year.is_current,
        "isFrozen": year.is_frozen,
        "isActive": year.is_active,
    }


def _batch_fp(batch_id) -> dict | None:
    if not batch_id:
        return None
    try:
        b = Batch.objects.select_related("academic_year").get(pk=batch_id)
        return {
            "id": str(b.pk),
            "version": b.version,
            "isActive": b.is_active,
            "academicYearId": str(b.academic_year_id),
            "name": b.name,
        }
    except Batch.DoesNotExist:
        return {"id": str(batch_id), "missing": True}


def _course_fp(course_id) -> dict | None:
    if not course_id:
        return None
    try:
        c = Course.objects.get(pk=course_id)
        return {"id": str(c.pk), "version": c.version, "isActive": c.is_active}
    except Course.DoesNotExist:
        return {"id": str(course_id), "missing": True}


def _fee_fp(structure_id) -> dict | None:
    if not structure_id:
        return None
    try:
        s = FeeStructure.objects.get(pk=structure_id)
        return {"id": str(s.pk), "version": s.version, "status": s.status, "isActive": s.is_active}
    except FeeStructure.DoesNotExist:
        return {"id": str(structure_id), "missing": True}


def build_fingerprint(session) -> dict:
    session = prep_q.require_approved_session(session.branch_id, session.pk) or session
    fp: dict = {
        "sourceYear": _year_fp(session.source_year),
        "targetYear": _year_fp(session.target_year),
        "classMappings": [],
        "decisions": [],
        "feeStructures": {},
    }
    for m in prep_q.list_class_mappings(session.pk):
        fp["classMappings"].append(
            {
                "sourceCourseId": str(m.source_course_id),
                "targetCourseId": str(m.target_course_id),
            }
        )
    for d in prep_q.list_decisions_with_profile(session.pk):
        profile = d.student_profile
        enr = StudentEnrollment.objects.filter(
            student_profile_id=profile.pk,
            academic_year_id=session.source_year_id,
            is_active=True,
        ).first()
        fp["decisions"].append(
            {
                "decisionId": str(d.pk),
                "profileId": str(profile.pk),
                "academicStatus": profile.academic_status,
                "currentBatchId": str(profile.current_batch_id) if profile.current_batch_id else None,
                "enrollmentId": str(enr.pk) if enr else None,
                "enrollmentStatus": enr.status if enr else None,
                "targetBatchId": str(d.target_batch_id) if d.target_batch_id else None,
                "executionReadiness": d.execution_readiness,
                "finalAction": d.final_action,
            }
        )
        if d.target_fee_structure_id:
            sid = str(d.target_fee_structure_id)
            if sid not in fp["feeStructures"]:
                fp["feeStructures"][sid] = _fee_fp(d.target_fee_structure_id)
    return fp


def _batch_drift(stored, live) -> str | None:
    if stored is None and live is None:
        return None
    if stored.get("missing") or live.get("missing"):
        return "A destination section was removed or is no longer available."
    if stored != live:
        return "A destination section was changed after preparation was locked."
    return None


def compare_fingerprints(stored: dict, live: dict) -> list[str]:
    if not stored:
        return ["Preparation fingerprint is missing."]
    changes: list[str] = []

    for label, key in (("Source academic year", "sourceYear"), ("Target academic year", "targetYear")):
        if stored.get(key) != live.get(key):
            changes.append(f"{label} was modified after preparation was locked.")

    stored_maps = {(m["sourceCourseId"], m["targetCourseId"]) for m in stored.get("classMappings", [])}
    live_maps = {(m["sourceCourseId"], m["targetCourseId"]) for m in live.get("classMappings", [])}
    if stored_maps != live_maps:
        changes.append("Class mappings were changed after preparation was locked.")

    stored_dec = {d["decisionId"]: d for d in stored.get("decisions", [])}
    live_dec = {d["decisionId"]: d for d in live.get("decisions", [])}
    for did, sd in stored_dec.items():
        ld = live_dec.get(did)
        if not ld:
            changes.append("A student decision was removed from the promotion plan.")
            continue
        if sd.get("academicStatus") != ld.get("academicStatus"):
            changes.append("A student was transferred or withdrawn after preparation was locked.")
        if sd.get("currentBatchId") != ld.get("currentBatchId"):
            changes.append("A student's current class was changed after preparation was locked.")
        msg = _batch_drift(
            _batch_fp(sd.get("targetBatchId")) if sd.get("targetBatchId") else None,
            _batch_fp(ld.get("targetBatchId")) if ld.get("targetBatchId") else None,
        )
        if msg and msg not in changes:
            changes.append(msg)

    for sid, sf in stored.get("feeStructures", {}).items():
        lf = live.get("feeStructures", {}).get(sid)
        if sf != lf:
            changes.append("A fee structure was edited after preparation was locked.")

    return changes


def check_and_apply_staleness(session, *, user=None) -> tuple[bool, list[str]]:
    """Return (is_stale, change_messages). Updates session if stale."""
    if session.preparation_status != PreparationStatus.LOCKED:
        return False, []

    stored = session.lock_fingerprint or {}
    live = build_fingerprint(session)
    changes = compare_fingerprints(stored, live)
    if not changes:
        return False, []

    from django.utils import timezone

    from apps.academics.queries import promotion_preparation as prep_q

    prep_q.update_session(
        session,
        {
            "preparation_status": PreparationStatus.INVALID,
            "staleness_detected_at": timezone.now(),
        },
        user=user,
    )
    prep_q.create_preparation_log(
        session=session,
        event=PreparationLogEvent.INVALIDATED,
        actor=user,
        reason="; ".join(changes[:5]),
        details={"changes": changes},
    )
    return True, changes
