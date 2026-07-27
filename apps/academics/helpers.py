"""Shared helpers for academics interactors and views."""

import datetime

from rest_framework.exceptions import PermissionDenied, ValidationError

from apps.accounts.models.user import Role, User
from apps.accounts.queries.user import get_active_user_in_tenant_with_role
from apps.organizations.models import InstitutionType


def institution_type(tenant) -> str:
    return tenant.institution_type


def is_school(tenant) -> bool:
    return institution_type(tenant) == InstitutionType.SCHOOL


def is_college(tenant) -> bool:
    return institution_type(tenant) == InstitutionType.COLLEGE


def batch_display_label(batch) -> str:
    """Human-readable class label, e.g. 'Class 5 - A' (not section letter alone)."""
    course = getattr(batch, "course", None)
    if course and getattr(course, "name", None):
        return f"{course.name} - {batch.name}"
    return batch.name


def tenant_has_multiple_branches(tenant_id) -> bool:
    from apps.organizations.models import Branch

    return Branch.objects.filter(tenant_id=tenant_id, is_active=True).count() > 1


def batch_homework_label(batch, tenant_id) -> str:
    """Class label for homework UIs — includes campus when the school has multiple branches."""
    label = batch_display_label(batch)
    if not tenant_has_multiple_branches(tenant_id):
        return label
    dept = getattr(getattr(batch, "course", None), "department", None)
    branch = getattr(dept, "branch", None)
    if branch and getattr(branch, "name", None):
        return f"{label} · {branch.name}"
    return label


def reject_class_teacher_for_college(tenant) -> None:
    if is_college(tenant):
        raise PermissionDenied("Class teacher assignment is only available for schools.")


def require_credits_for_college(tenant, credits) -> None:
    if is_college(tenant) and credits is None:
        raise ValidationError({"credits": "Credits are required for college subjects."})


def check_version(instance, expected_version: int | None) -> None:
    if expected_version is None:
        return
    if instance.version != expected_version:
        raise ValidationError(
            {"version": "Record was modified by another user. Refresh and try again."}
        )


def get_faculty_user(tenant_id, faculty_id) -> User | None:
    if not faculty_id:
        return None
    return get_active_user_in_tenant_with_role(tenant_id, faculty_id, Role.FACULTY)


def require_faculty(tenant_id, faculty_id, field_name: str = "facultyId") -> User:
    """Return an active faculty user or raise a field ValidationError."""
    user = get_faculty_user(tenant_id, faculty_id)
    if user is not None:
        return user

    # Distinguish inactive vs missing so admins get an actionable message.
    inactive = (
        User.objects.filter(
            pk=faculty_id,
            tenant_id=tenant_id,
            role=Role.FACULTY,
            is_active=False,
        ).first()
        if faculty_id
        else None
    )
    if inactive is not None:
        raise ValidationError({field_name: "Faculty account is inactive and cannot be assigned."})
    raise ValidationError({field_name: "Faculty user not found in your institution."})


def date_to_iso_weekday(d: datetime.date) -> int:
    """Return ISO weekday for a calendar date (Mon=1 … Sun=7)."""
    return d.isoweekday()


def js_day_to_iso(js_day: int) -> int:
    """Convert JS getDay() (Sun=0 … Sat=6) to ISO (Mon=1 … Sun=7)."""
    return 7 if js_day == 0 else js_day


def iso_to_js_day(iso_day: int) -> int:
    """Convert ISO weekday (Mon=1 … Sun=7) to JS getDay() (Sun=0 … Sat=6)."""
    return 0 if iso_day == 7 else iso_day


def entry_matches_date(entry_day_of_week: int, on_date: datetime.date) -> bool:
    """True when a timetable entry's day_of_week matches the calendar date."""
    return int(entry_day_of_week) == date_to_iso_weekday(on_date)
