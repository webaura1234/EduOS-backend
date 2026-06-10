"""Interactors — Academic year rollover (Flow 7)."""

from __future__ import annotations

import datetime

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.academics.dtos import RolloverPreviewDTO, RolloverStudentPreviewDTO
from apps.academics.helpers import is_college
from apps.academics.models import PeriodType, RolloverRunStatus
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import rollover as rol_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import timetable as tt_q
from apps.organizations.models import Branch

ROLLOVER_ASYNC_THRESHOLD = 200


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

    students = rol_q.list_students_in_year(branch_id, current.pk)
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

    for profile in students:
        batch = profile.current_batch
        if not batch:
            continue
        next_course = _get_next_course(batch.course.department_id, batch.course_id)
        if next_course is None:
            promotions.append(
                RolloverStudentPreviewDTO(
                    student_id=str(profile.user_id),
                    name=profile.user.full_name,
                    from_class=_batch_label(batch),
                    to_class="Graduated",
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

    students = rol_q.list_students_in_year(branch.pk, current.pk)
    for profile in students:
        batch = profile.current_batch
        if not batch:
            continue
        next_course = _get_next_course(batch.course.department_id, batch.course_id)
        if next_course is None:
            rol_q.graduate_student(profile, user=user)
            continue
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
        rol_q.set_student_batch(profile, dest.pk, user=user)

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
    students = rol_q.list_students_in_year(branch_id, year_id)
    return {
        "student_batches": {str(s.user_id): str(s.current_batch_id) if s.current_batch_id else None for s in students},
        "student_statuses": {str(s.user_id): s.academic_status for s in students},
        "current_year_id": str(year_id),
    }


@transaction.atomic
def undo_rollover(*, branch_id, user=None):
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
