"""Shared helpers for academics interactors and views."""

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
    user = get_faculty_user(tenant_id, faculty_id)
    if user is None:
        raise ValidationError({field_name: "Faculty user not found in your institution."})
    return user
