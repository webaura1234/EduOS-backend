"""Queries — which faculty can substitute for a timetable session on a given date."""

import datetime

from apps.academics.models import AcademicSubstitution
from apps.academics.queries import timetable as tt_q
from apps.accounts.models.user import Role, User
from apps.hr.queries import employee as emp_q
from apps.hr.queries import leave as leave_q

_UNASSIGNED_FACULTY = "__unassigned__"


def _faculty_on_approved_leave(user_id, on_date: datetime.date) -> bool:
    emp = emp_q.get_employee_for_user(user_id)
    if not emp:
        return False
    return on_date in leave_q.approved_leave_dates(emp.pk, on_date, on_date)


def _faculty_teaching_at_period(branch_id, faculty_id, day_of_week, period_slot_id, *, exclude_entry_id=None) -> bool:
    clashes = tt_q.find_clashing_entries(
        branch_id,
        day_of_week=day_of_week,
        period_slot_id=period_slot_id,
        faculty_id=faculty_id,
        exclude_entry_id=exclude_entry_id,
    )
    return bool(clashes)


def _faculty_substituting_at_period(
    branch_id,
    faculty_id,
    on_date: datetime.date,
    day_of_week,
    period_slot_id,
) -> bool:
    subs = (
        AcademicSubstitution.objects.filter(
            branch_id=branch_id,
            substitute_faculty_id=faculty_id,
            date=on_date,
            is_active=True,
        )
        .exclude(status="cancelled")
        .select_related("timetable_entry")
    )
    for sub in subs:
        entry = sub.timetable_entry
        if entry.day_of_week == day_of_week and entry.period_slot_id == period_slot_id:
            return True
    return False


def is_faculty_available_for_substitution(*, branch, faculty_user, timetable_entry, on_date: datetime.date) -> bool:
    """True when faculty can cover this session on the given calendar date."""
    if not faculty_user or not faculty_user.is_active:
        return False
    if timetable_entry.faculty_id and faculty_user.pk == timetable_entry.faculty_id:
        return False
    period_slot_id = timetable_entry.period_slot_id
    if _faculty_teaching_at_period(
        branch.pk,
        faculty_user.pk,
        timetable_entry.day_of_week,
        period_slot_id,
        exclude_entry_id=timetable_entry.pk,
    ):
        return False
    if _faculty_on_approved_leave(faculty_user.pk, on_date):
        return False
    if _faculty_substituting_at_period(
        branch.pk,
        faculty_user.pk,
        on_date,
        timetable_entry.day_of_week,
        period_slot_id,
    ):
        return False
    return True


def _slot_payload(entry) -> dict:
    period = entry.period_slot
    subject_id = (
        str(entry.batch_subject.subject_id)
        if entry.batch_subject_id
        else "__tbd__"
    )
    return {
        "id": str(entry.pk),
        "classSectionId": str(entry.timetable.batch_id),
        "subjectId": subject_id,
        "periodIndex": period.sequence if period else 0,
        "startTime": period.start_time.isoformat() if period else "",
        "endTime": period.end_time.isoformat() if period else "",
    }


def available_substitute_faculty(*, branch, timetable_entry, on_date: datetime.date) -> dict:
    """Return original teacher + faculty free at this session's day/period on `on_date`."""
    original = timetable_entry.faculty
    faculty_users = User.objects.filter(
        tenant=branch.tenant,
        branch=branch,
        role=Role.FACULTY,
        is_active=True,
    ).order_by("first_name", "last_name", "id")

    available = []
    for user in faculty_users:
        if is_faculty_available_for_substitution(
            branch=branch,
            faculty_user=user,
            timetable_entry=timetable_entry,
            on_date=on_date,
        ):
            available.append({
                "userId": str(user.pk),
                "name": user.full_name or user.username or str(user.pk),
            })

    return {
        "originalFacultyUserId": str(original.pk) if original else _UNASSIGNED_FACULTY,
        "originalFacultyName": (original.full_name or original.username) if original else "Unassigned",
        "slot": _slot_payload(timetable_entry),
        "availableFaculty": available,
    }
