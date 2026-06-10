"""Interactors — AcademicYear and AcademicPeriod."""

from datetime import timedelta

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.academics.helpers import check_version
from apps.academics.queries import calendar as cal_q


def _ensure_not_frozen(year) -> None:
    if year.is_frozen:
        raise ValidationError("This academic year is frozen and cannot be modified.")


def _validate_dates(start_date, end_date) -> None:
    if end_date <= start_date:
        raise ValidationError({"endDate": "End date must be after start date."})


def _period_within_year(period, year) -> None:
    if period.start_date < year.start_date or period.end_date > year.end_date:
        raise ValidationError("Period dates must fall within the academic year.")


@transaction.atomic
def create_academic_year(branch_id, *, name, start_date, end_date, is_current=False, user=None):
    _validate_dates(start_date, end_date)
    if cal_q.year_name_exists(branch_id, name):
        raise ValidationError({"name": "An academic year with this name already exists."})
    return cal_q.create_year(
        branch_id, name=name, start_date=start_date, end_date=end_date, is_current=is_current, user=user
    )


@transaction.atomic
def update_academic_year(year, *, fields: dict, user=None):
    _ensure_not_frozen(year)
    check_version(year, fields.pop("version", None))
    start = fields.get("start_date", year.start_date)
    end = fields.get("end_date", year.end_date)
    _validate_dates(start, end)
    name = fields.get("name", year.name)
    if cal_q.year_name_exists(year.branch_id, name, exclude_id=year.pk):
        raise ValidationError({"name": "An academic year with this name already exists."})
    return cal_q.update_year(year, fields, user=user)


@transaction.atomic
def academic_year_action(*, year, action: str, user=None):
    if action == "set_current":
        return cal_q.set_current_year(year, user=user)
    if action == "freeze":
        return cal_q.freeze_year(year, user=user)
    raise ValidationError({"action": "Unknown action."})


@transaction.atomic
def create_academic_period(year, *, period_type, sequence, name, start_date, end_date, user=None):
    _ensure_not_frozen(year)
    _validate_dates(start_date, end_date)
    from apps.academics.models import AcademicPeriod

    period = AcademicPeriod(
        academic_year=year,
        period_type=period_type,
        sequence=sequence,
        name=name,
        start_date=start_date,
        end_date=end_date,
    )
    _period_within_year(period, year)
    if cal_q.period_sequence_exists(year.pk, sequence):
        raise ValidationError({"sequence": "A period with this sequence already exists."})
    return cal_q.create_period(
        year.pk,
        period_type=period_type,
        sequence=sequence,
        name=name,
        start_date=start_date,
        end_date=end_date,
        user=user,
    )


@transaction.atomic
def update_academic_period(period, year, *, fields: dict, user=None):
    _ensure_not_frozen(year)
    check_version(period, fields.pop("version", None))
    start = fields.get("start_date", period.start_date)
    end = fields.get("end_date", period.end_date)
    _validate_dates(start, end)
    from apps.academics.models import AcademicPeriod

    probe = AcademicPeriod(
        academic_year=year,
        start_date=start,
        end_date=end,
    )
    _period_within_year(probe, year)
    seq = fields.get("sequence", period.sequence)
    if cal_q.period_sequence_exists(year.pk, seq, exclude_id=period.pk):
        raise ValidationError({"sequence": "A period with this sequence already exists."})
    return cal_q.update_period(period, fields, user=user)


@transaction.atomic
def delete_academic_period(period, year, user=None):
    _ensure_not_frozen(year)
    return cal_q.soft_delete_period(period, user=user)
