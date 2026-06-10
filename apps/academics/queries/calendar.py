"""
Queries — AcademicYear and AcademicPeriod (all DB access for the calendar).
"""

from django.db import transaction
from django.utils import timezone

from apps.academics.models import AcademicPeriod, AcademicYear


def list_years(branch_id):
    return AcademicYear.objects.filter(branch_id=branch_id, is_active=True).order_by("-start_date")


def get_year(branch_id, year_id) -> AcademicYear | None:
    try:
        return AcademicYear.objects.get(branch_id=branch_id, pk=year_id, is_active=True)
    except (AcademicYear.DoesNotExist, ValueError, TypeError):
        return None


def get_current_year(branch_id) -> AcademicYear | None:
    try:
        return AcademicYear.objects.get(branch_id=branch_id, is_current=True, is_active=True)
    except AcademicYear.DoesNotExist:
        return None


def year_name_exists(branch_id, name, exclude_id=None) -> bool:
    qs = AcademicYear.objects.filter(branch_id=branch_id, name__iexact=name, is_active=True)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def create_year(branch_id, *, name, start_date, end_date, is_current=False, user=None) -> AcademicYear:
    with transaction.atomic():
        if is_current:
            AcademicYear.objects.filter(branch_id=branch_id, is_current=True).update(is_current=False)
        return AcademicYear.objects.create(
            branch_id=branch_id,
            name=name,
            start_date=start_date,
            end_date=end_date,
            is_current=is_current,
            created_by=user,
            updated_by=user,
        )


def update_year(year: AcademicYear, fields: dict, user=None) -> AcademicYear:
    for k, v in fields.items():
        setattr(year, k, v)
    if fields:
        year.version += 1
        if user:
            year.updated_by = user
        year.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return year


def set_current_year(year: AcademicYear, user=None) -> AcademicYear:
    with transaction.atomic():
        AcademicYear.objects.filter(branch_id=year.branch_id, is_current=True).exclude(
            pk=year.pk
        ).update(is_current=False)
        year.is_current = True
        year.version += 1
        if user:
            year.updated_by = user
        year.save(update_fields=["is_current", "version", "updated_by", "updated_at"])
    return year


def freeze_year(year: AcademicYear, user=None) -> AcademicYear:
    year.is_frozen = True
    year.version += 1
    if user:
        year.updated_by = user
    year.save(update_fields=["is_frozen", "version", "updated_by", "updated_at"])
    return year


def soft_delete_year(year: AcademicYear, user=None) -> AcademicYear:
    year.soft_delete(user)
    year.version += 1
    year.save(update_fields=["version", "updated_at"])
    return year


# ── AcademicPeriod ────────────────────────────────────────────────────────────
def list_periods(year_id):
    return AcademicPeriod.objects.filter(academic_year_id=year_id, is_active=True).order_by("sequence")


def get_period(year_id, period_id) -> AcademicPeriod | None:
    try:
        return AcademicPeriod.objects.get(academic_year_id=year_id, pk=period_id, is_active=True)
    except (AcademicPeriod.DoesNotExist, ValueError, TypeError):
        return None


def period_sequence_exists(year_id, sequence, exclude_id=None) -> bool:
    qs = AcademicPeriod.objects.filter(academic_year_id=year_id, sequence=sequence, is_active=True)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def create_period(year_id, *, period_type, sequence, name, start_date, end_date, user=None) -> AcademicPeriod:
    return AcademicPeriod.objects.create(
        academic_year_id=year_id,
        period_type=period_type,
        sequence=sequence,
        name=name,
        start_date=start_date,
        end_date=end_date,
        created_by=user,
        updated_by=user,
    )


def update_period(period: AcademicPeriod, fields: dict, user=None) -> AcademicPeriod:
    for k, v in fields.items():
        setattr(period, k, v)
    if fields:
        period.version += 1
        if user:
            period.updated_by = user
        period.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return period


def soft_delete_period(period: AcademicPeriod, user=None) -> AcademicPeriod:
    period.soft_delete(user)
    period.version += 1
    period.save(update_fields=["version", "updated_at"])
    return period
