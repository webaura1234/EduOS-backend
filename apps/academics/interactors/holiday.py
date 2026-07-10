"""Interactors — Holiday calendar."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.academics.helpers import check_version
from apps.academics.queries import holiday as hol_q


@transaction.atomic
def create_holiday(branch_id, *, date, name, holiday_type, applies_to=None, user=None):
    existing = hol_q.get_holiday_by_date(branch_id, date)
    if existing is not None:
        if existing.is_active:
            raise ValidationError({"date": "A holiday already exists on this date."})
        return hol_q.restore_holiday(
            existing,
            name=name,
            holiday_type=holiday_type,
            applies_to=applies_to,
            user=user,
        )
    return hol_q.create_holiday(
        branch_id, date=date, name=name, holiday_type=holiday_type,
        applies_to=applies_to, user=user,
    )


@transaction.atomic
def update_holiday(holiday, *, fields: dict, user=None):
    check_version(holiday, fields.pop("version", None))
    date = fields.get("date", holiday.date)
    conflict = hol_q.get_holiday_by_date(holiday.branch_id, date)
    if conflict and conflict.pk != holiday.pk:
        if conflict.is_active:
            raise ValidationError({"date": "A holiday already exists on this date."})
        conflict.delete()
    return hol_q.update_holiday(holiday, fields, user=user)


@transaction.atomic
def delete_holiday(holiday, user=None):
    return hol_q.soft_delete_holiday(holiday, user=user)
