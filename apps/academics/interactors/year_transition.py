"""Shared academic year transition helpers (Phase 3 promotion + future rollover reuse)."""

from __future__ import annotations

from apps.academics.queries import calendar as cal_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import timetable as tt_q
from apps.admissions.enums import EnrollmentStatus
from apps.admissions.queries import enrollment as enr_q


def activate_target_year(*, branch_id, source_year, target_year, user=None):
    """Freeze source year and set target as current (single current year per branch)."""
    cal_q.freeze_year(source_year, user=user)
    cal_q.set_current_year(target_year, user=user)


def deactivate_source_enrollment(enrollment, *, terminal_status: str | None = None, user=None):
    """Deactivate source-year enrollment while preserving historical record."""
    fields = {"is_active": False}
    if terminal_status:
        fields["status"] = terminal_status
    elif enrollment.status == EnrollmentStatus.ACTIVE:
        fields["status"] = EnrollmentStatus.ACTIVE
    return enr_q.update_enrollment(enrollment, fields, user=user)


def complete_timetable_rollover(*, branch_id, source_year_id, target_year_id, user=None):
    """Soft-delete old timetable entries and seed empty timetables for target year batches."""
    tt_q.soft_delete_timetable_entries_for_branch_year(branch_id, source_year_id, user=user)
    target_batches = struct_q.list_batches(branch_id, academic_year_id=target_year_id)
    periods = list(cal_q.list_periods(target_year_id))
    if not periods:
        return
    for batch in target_batches:
        for period in periods:
            tt_q.get_or_create_timetable(batch=batch, academic_period=period, user=user)
