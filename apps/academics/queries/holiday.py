"""Queries — Holiday calendar."""

import datetime

from apps.academics.models import Holiday


def list_holidays(branch_id, *, from_date=None, to_date=None):
    qs = Holiday.objects.filter(branch_id=branch_id, is_active=True).order_by("date")
    if from_date:
        qs = qs.filter(date__gte=from_date)
    if to_date:
        qs = qs.filter(date__lte=to_date)
    return qs


def get_holiday(branch_id, holiday_id) -> Holiday | None:
    try:
        return Holiday.objects.get(branch_id=branch_id, pk=holiday_id, is_active=True)
    except (Holiday.DoesNotExist, ValueError, TypeError):
        return None


def holiday_date_exists(branch_id, date, exclude_id=None) -> bool:
    qs = Holiday.objects.filter(branch_id=branch_id, date=date, is_active=True)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def is_holiday(branch_id, date: datetime.date) -> bool:
    return Holiday.objects.filter(branch_id=branch_id, date=date, is_active=True).exists()


def create_holiday(branch_id, *, date, name, holiday_type, applies_to=None, user=None) -> Holiday:
    return Holiday.objects.create(
        branch_id=branch_id,
        date=date,
        name=name,
        holiday_type=holiday_type,
        applies_to=applies_to or {"all": True},
        created_by=user,
        updated_by=user,
    )


def update_holiday(holiday: Holiday, fields: dict, user=None) -> Holiday:
    for k, v in fields.items():
        setattr(holiday, k, v)
    if fields:
        holiday.version += 1
        if user:
            holiday.updated_by = user
        holiday.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return holiday


def soft_delete_holiday(holiday: Holiday, user=None) -> Holiday:
    holiday.soft_delete(user)
    holiday.version += 1
    holiday.save(update_fields=["version", "updated_at"])
    return holiday
