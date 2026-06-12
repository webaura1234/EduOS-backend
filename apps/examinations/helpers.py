"""Shared helpers for examinations interactors and serializers."""

import datetime

from django.utils import timezone
from rest_framework.exceptions import ValidationError


def parse_time(value: str, *, field: str = "time") -> datetime.time:
    """Parse HH:MM or HH:MM:SS into a time."""
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.datetime.strptime(value, fmt).time()
        except ValueError:
            continue
    raise ValidationError({field: "Time must be in HH:MM format."})


def combine_datetime(date: datetime.date, time_value: datetime.time) -> datetime.datetime:
    """Combine date + time into a timezone-aware datetime."""
    naive = datetime.datetime.combine(date, time_value)
    if timezone.is_naive(naive):
        return timezone.make_aware(naive)
    return naive


def split_datetime(dt: datetime.datetime) -> tuple[str, str, str]:
    """Return (YYYY-MM-DD, HH:MM, HH:MM) for a datetime pair's start."""
    local = timezone.localtime(dt)
    return local.date().isoformat(), local.strftime("%H:%M"), local.strftime("%H:%M")


def validate_bands(bands) -> None:
    if not isinstance(bands, list) or not bands:
        raise ValidationError({"bands": "At least one grade band is required."})
    for band in bands:
        if not isinstance(band, dict):
            raise ValidationError({"bands": "Each band must be an object."})
        for key in ("minPercent", "maxPercent", "grade"):
            if key not in band:
                raise ValidationError({"bands": f"Each band requires {key}."})
        min_p = band["minPercent"]
        max_p = band["maxPercent"]
        if not isinstance(min_p, (int, float)) or not isinstance(max_p, (int, float)):
            raise ValidationError({"bands": "minPercent and maxPercent must be numbers."})
        if min_p > max_p:
            raise ValidationError({"bands": "minPercent cannot exceed maxPercent."})


def parse_marks_value(raw, *, is_absent: bool):
    from decimal import Decimal, InvalidOperation

    if is_absent:
        return None
    if raw is None:
        raise ValidationError({"marks": "Marks are required unless the student is absent."})
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        raise ValidationError({"marks": "Marks must be a number."}) from None
    if value < 0:
        raise ValidationError({"marks": "Marks cannot be negative."})
    return value


def validate_marks_against_max(marks, *, max_marks, is_absent: bool) -> None:
    if is_absent or marks is None:
        return
    if marks > max_marks:
        raise ValidationError({"marks": f"Marks cannot exceed {max_marks}."})


def is_conflict_of_interest(actor, student_profile) -> bool:
    from apps.examinations.queries import marks as marks_q

    return marks_q.student_linked_to_faculty_group(actor, student_profile)


def is_admin_role(user) -> bool:
    from apps.accounts.models.user import Role

    return user.role in {Role.ADMIN, Role.SUPER_ADMIN}
