"""Interactors — Legacy standalone rollover engine (Flow 7).

Not a user-facing entry point. Academic Year Promotion is the sole execution path.
Internal helpers remain for regression tests and shared enrollment/year logic.
"""

from __future__ import annotations

import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.academics.dtos import RolloverPreviewDTO, RolloverStudentPreviewDTO
from apps.academics.exceptions import RolloverDirectExecutionDisabledError
from apps.academics.helpers import is_college
from apps.academics.interactors.year_transition import deactivate_source_enrollment
from apps.academics.models import PeriodType, RolloverRunStatus
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import rollover as rol_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import timetable as tt_q
from apps.admissions.queries import enrollment as enr_q
from apps.admissions.enums import EnrollmentStatus
from apps.examinations.queries import marks as exam_marks_q
from apps.organizations.models import Branch

ROLLOVER_ASYNC_THRESHOLD = 200


def _ensure_direct_rollover_allowed() -> None:
    """Block standalone rollover — promotion is the only admin execution path."""
    raise RolloverDirectExecutionDisabledError()


def _assert_no_conflicting_promotion(branch_id) -> None:
    """Reject rollover when promotion owns the same branch/year transition."""
    from apps.academics.models.promotion import (
        AcademicPromotionSession,
        PromotionExecutionStatus,
        PromotionSessionStatus,
    )

    if AcademicPromotionSession.objects.filter(
        branch_id=branch_id,
        execution_status=PromotionExecutionStatus.RUNNING,
        is_active=True,
    ).exists():
        raise ValidationError(
            "Cannot run standalone rollover while promotion execution is in progress."
        )

    current = cal_q.get_current_year(branch_id)
    if current and AcademicPromotionSession.objects.filter(
        branch_id=branch_id,
        source_year_id=current.pk,
        status=PromotionSessionStatus.APPROVED,
        is_active=True,
    ).exists():
        raise ValidationError(
            "Cannot run standalone rollover while an approved promotion session exists. "
            "Use Academic Year Promotion instead."
        )


def _shift_year(d: datetime.date, years: int = 1) -> datetime.date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:
        return d.replace(year=d.year + years, day=28)


def _next_year_label(name: str) -> str:
    """Best-effort label shift e.g. 2024-25 → 2025-26."""
    if "-" in name:
        parts = name.split("-")
        try:
            start = int(parts[0])
            return f"{start + 1}-{start + 2}"
        except ValueError:
            pass
    return f"{name} (next)"


def _get_next_course(department_id, current_course_id):
    courses = list(struct_q.list_courses_in_department_ordered(department_id))
    ids = [c.pk for c in courses]
    if current_course_id not in ids:
        return None
    idx = ids.index(current_course_id)
    if idx + 1 < len(courses):
        return courses[idx + 1]
    return None


def _batch_label(batch) -> str:
    return f"{batch.course.name} — {batch.name}"


def build_preview(branch_id, tenant) -> RolloverPreviewDTO:
    current = cal_q.get_current_year(branch_id)
    if not current:
        raise ValidationError("No current academic year found for this branch.")
    if current.is_frozen:
        raise ValidationError("Current academic year is already frozen.")

    students = rol_q.list_enrollments_in_year(branch_id, current.pk)
    promotions: list[RolloverStudentPreviewDTO] = []
    warnings = [
        "Faculty timetable will need regeneration after rollover.",
        "Fee templates will not be copied until the Fees module is available.",
    ]
    if is_college(tenant):
        warnings.append(
            "College students with open arrears will be listed in preview; "
            "full arrear enrollment copy requires the Examinations module (EC-ROL-05)."
        )

    college = is_college(tenant)
    for enrollment in students:
        profile = enrollment.student_profile
        batch = enrollment.batch
        if not batch:
            continue
        next_course = _get_next_course(batch.course.department_id, batch.course_id)
        if next_course is None:
            # Final year: graduates unless college arrears remain (EC-ROL-05).
            to_class = "Graduated"
            if college:
                if exam_marks_q.open_arrear_subjects(enrollment.pk):
                    to_class = "Retained (arrears pending)"
            promotions.append(
                RolloverStudentPreviewDTO(
                    student_id=str(profile.user_id),
                    name=profile.user.full_name,
                    from_class=_batch_label(batch),
                    to_class=to_class,
                )
            )
        else:
            promotions.append(
                RolloverStudentPreviewDTO(
                    student_id=str(profile.user_id),
                    name=profile.user.full_name,
                    from_class=_batch_label(batch),
                    to_class=f"{next_course.name} — {batch.name}",
                )
            )

    latest = rol_q.get_latest_rollover_run(branch_id)
    version = (latest.preview_version + 1) if latest else 1

    return RolloverPreviewDTO(
        from_year_label=current.name,
        to_year_label=_next_year_label(current.name),
        students_to_promote=promotions,
        warnings=warnings,
        version=version,
    )


@transaction.atomic
def execute_rollover(*, branch: Branch, tenant, expected_version: int, user=None):
    _ensure_direct_rollover_allowed()
    _assert_no_conflicting_promotion(branch.pk)
    preview = build_preview(branch.pk, tenant)
    if preview.version != expected_version:
        raise ValidationError(
            {"expectedVersion": "Rollover preview is stale. Refresh and try again."}
        )

    current = cal_q.get_current_year(branch.pk)
    assert current

    student_count = rol_q.count_students_in_year(branch.pk, current.pk)
    if student_count > ROLLOVER_ASYNC_THRESHOLD:
        run = rol_q.create_rollover_run(
            branch=branch, from_year=current, preview_version=expected_version, user=user
        )
        rol_q.update_rollover_run(run, {"status": RolloverRunStatus.RUNNING}, user=user)
        from apps.academics.tasks import execute_rollover_task

        execute_rollover_task.delay(str(run.pk))
        return {"jobId": str(run.pk), "status": "running", "async": True}

    return _execute_rollover_sync(
        branch=branch, tenant=tenant, user=user, expected_version=expected_version, existing_run=None,
    )


@transaction.atomic
def _execute_rollover_sync(
    *, branch: Branch, tenant, expected_version: int, user=None, existing_run=None,
):
    current = cal_q.get_current_year(branch.pk)
    if not current:
        raise ValidationError("No current academic year.")

    snapshot = _capture_snapshot(branch.pk, current.pk)

    new_start = _shift_year(current.start_date)
    new_end = _shift_year(current.end_date)
    new_name = _next_year_label(current.name)

    if cal_q.year_name_exists(branch.pk, new_name):
        raise ValidationError({"toYear": f"Academic year {new_name} already exists."})

    if existing_run:
        run = existing_run
    else:
        run = rol_q.create_rollover_run(
            branch=branch, from_year=current, preview_version=expected_version, user=user
        )
    rol_q.update_rollover_run(run, {"status": RolloverRunStatus.RUNNING}, user=user)

    new_year = cal_q.create_year(
        branch.pk,
        name=new_name,
        start_date=new_start,
        end_date=new_end,
        is_current=True,
        user=user,
    )

    period_type = PeriodType.SEMESTER if is_college(tenant) else PeriodType.TERM
    old_periods = list(cal_q.list_periods(current.pk))
    new_periods = []
    for p in old_periods:
        np = cal_q.create_period(
            new_year.pk,
            period_type=p.period_type or period_type,
            sequence=p.sequence,
            name=p.name,
            start_date=_shift_year(p.start_date),
            end_date=_shift_year(p.end_date),
            user=user,
        )
        new_periods.append((p.pk, np))

    cal_q.freeze_year(current, user=user)
    cal_q.set_current_year(new_year, user=user)

    batch_map: dict = {}
    old_batches = struct_q.list_batches(branch.pk, academic_year_id=current.pk)
    for ob in old_batches:
        nb = struct_q.create_batch(
            course=ob.course,
            academic_year=new_year,
            name=ob.name,
            capacity=ob.capacity,
            class_teacher_id=ob.class_teacher_id,
            user=user,
        )
        batch_map[str(ob.pk)] = str(nb.pk)

    college = is_college(tenant)
    students = rol_q.list_enrollments_in_year(branch.pk, current.pk)
    student_actions: list[dict] = []
    for enrollment in students:
        profile = enrollment.student_profile
        batch = enrollment.batch
        if not batch:
            continue

        # Carried-forward arrears (college only), derived from the prior-year enrollment.
        backlog: list[dict] = []
        if college:
            backlog = exam_marks_q.open_arrear_subjects(enrollment.pk)

        prior_batch_id = str(batch.pk)
        prior_status = profile.academic_status
        next_course = _get_next_course(batch.course.department_id, batch.course_id)

        if next_course is None:
            if backlog:
                # Final-year with open arrears: retained in the same final batch (new-year
                # equivalent) to re-sit; NOT graduated until backlog clears (EC-ROL-05).
                dest = struct_q.get_batch(branch.pk, batch_map[str(batch.pk)])
                deactivate_source_enrollment(enrollment, user=user)
                new_enr = enr_q.create_enrollment(
                    branch=branch, student_profile=profile, batch=dest,
                    academic_year=new_year, backlog_subjects=backlog, user=user,
                )
                rol_q.sync_current_enrollment(profile, new_enr, user=user)
                rol_q.set_student_batch(profile, dest.pk, user=user)
                action, new_enr_id, new_batch_id = "retained_arrear", str(new_enr.pk), str(dest.pk)
            else:
                from apps.admissions.enums import EnrollmentStatus

                deactivate_source_enrollment(
                    enrollment, terminal_status=EnrollmentStatus.GRADUATED, user=user
                )
                rol_q.sync_current_enrollment(profile, enrollment, user=user)
                rol_q.graduate_student(profile, user=user)
                action, new_enr_id, new_batch_id = "graduated", None, None
        else:
            dest_qs = struct_q.list_batches(
                branch.pk, course_id=next_course.pk, academic_year_id=new_year.pk
            )
            dest = dest_qs.filter(name=batch.name).first()
            if not dest:
                dest = struct_q.create_batch(
                    course=next_course,
                    academic_year=new_year,
                    name=batch.name,
                    capacity=batch.capacity,
                    class_teacher_id=batch.class_teacher_id,
                    user=user,
                )
            deactivate_source_enrollment(enrollment, user=user)
            new_enr = enr_q.create_enrollment(
                branch=branch, student_profile=profile, batch=dest,
                academic_year=new_year, backlog_subjects=backlog, user=user,
            )
            rol_q.sync_current_enrollment(profile, new_enr, user=user)
            rol_q.set_student_batch(profile, dest.pk, user=user)
            action, new_enr_id, new_batch_id = "promoted", str(new_enr.pk), str(dest.pk)

        student_actions.append({
            "student_profile_id": str(profile.pk),
            "user_id": str(profile.user_id),
            "prior_current_batch_id": prior_batch_id,
            "prior_academic_status": prior_status,
            "prior_enrollment_id": str(enrollment.pk),
            "action": action,
            "new_enrollment_id": new_enr_id,
            "new_batch_id": new_batch_id,
            "backlog_subjects": backlog,
        })

    snapshot["student_actions"] = student_actions

    tt_q.soft_delete_timetable_entries_for_branch_year(branch.pk, current.pk, user=user)

    new_batches = rol_q.get_batches_by_ids(list(batch_map.values()))
    for _, np in new_periods:
        for b in new_batches:
            tt_q.get_or_create_timetable(batch=b, academic_period=np, user=user)

    now = timezone.now()
    rol_q.update_rollover_run(
        run,
        {
            "status": RolloverRunStatus.SUCCEEDED,
            "to_year": new_year,
            "snapshot": snapshot,
            "executed_at": now,
            "executed_by": user,
            "undo_expires_at": rol_q.set_undo_expiry(24),
        },
        user=user,
    )

    return {
        "status": "succeeded",
        "async": False,
        "runId": str(run.pk),
        "toYearId": str(new_year.pk),
        "undoExpiresAt": run.undo_expires_at.isoformat() if run.undo_expires_at else None,
    }


def _capture_snapshot(branch_id, year_id) -> dict:
    enrollments = rol_q.list_enrollments_in_year(branch_id, year_id)
    return {
        "student_batches": {
            str(e.student_profile.user_id): str(e.batch_id) if e.batch_id else None
            for e in enrollments
        },
        "student_statuses": {
            str(e.student_profile.user_id): e.student_profile.academic_status for e in enrollments
        },
        "current_year_id": str(year_id),
    }


@transaction.atomic
def undo_rollover(*, branch_id, user=None):
    _ensure_direct_rollover_allowed()
    return _undo_rollover_impl(branch_id=branch_id, user=user)


@transaction.atomic
def _undo_rollover_impl(*, branch_id, user=None):
    run = rol_q.get_latest_rollover_run(branch_id)
    if not run or run.status != RolloverRunStatus.SUCCEEDED:
        raise ValidationError("Nothing to undo.")
    if not rol_q.undo_window_active(run):
        raise PermissionDenied("Undo window has expired (24 hours).")

    snap = run.snapshot or {}
    from apps.accounts.models.profile import AcademicStatus

    statuses = snap.get("student_statuses", {})
    for sid, batch_id in snap.get("student_batches", {}).items():
        profile = rol_q.get_student_profile(sid)
        if profile is None:
            continue
        rol_q.restore_student(
            profile,
            batch_id=batch_id,
            academic_status=statuses.get(sid, AcademicStatus.ACTIVE),
            user=user,
        )

    # Soft-delete the enrollments this run created (EC-ROL-02).
    for act in snap.get("student_actions", []):
        if act.get("new_enrollment_id"):
            enr_q.soft_delete_enrollment_by_id(act["new_enrollment_id"], user=user)
        prior_id = act.get("prior_enrollment_id")
        if prior_id:
            prior = enr_q.get_enrollment_by_id(prior_id, include_inactive=True)
            if prior:
                enr_q.update_enrollment(
                    prior,
                    {"is_active": True, "status": EnrollmentStatus.ACTIVE},
                    user=user,
                )
                profile = rol_q.get_student_profile(act.get("user_id"))
                if profile:
                    rol_q.sync_current_enrollment(profile, prior, user=user)

    # Order matters: drop the new year's current flag BEFORE reactivating the old
    # one, or the unique-current-year constraint would be violated.
    if run.to_year_id:
        ty = rol_q.get_academic_year(run.to_year_id)
        if ty:
            rol_q.deactivate_rolled_year(ty, user=user)
    if run.from_year_id:
        fy = rol_q.get_academic_year(run.from_year_id)
        if fy:
            rol_q.reactivate_year(fy, user=user)

    rol_q.update_rollover_run(
        run, {"status": RolloverRunStatus.COMPENSATED, "undo_expires_at": None}, user=user
    )
    return {"status": "compensated", "runId": str(run.pk)}


def get_rollover_status(branch_id) -> dict:
    run = rol_q.get_latest_rollover_run(branch_id)
    if not run:
        return {
            "lastRolloverAt": None,
            "undoExpiresAt": None,
            "canUndo": False,
            "status": None,
        }
    return {
        "lastRolloverAt": run.executed_at.isoformat() if run.executed_at else None,
        "undoExpiresAt": run.undo_expires_at.isoformat() if run.undo_expires_at else None,
        "canUndo": rol_q.undo_window_active(run),
        "status": run.status,
        "runId": str(run.pk),
    }
