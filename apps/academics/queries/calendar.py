"""
Queries — AcademicYear and AcademicPeriod (all DB access for the calendar).
"""

from django.db import transaction

from apps.academics.models import AcademicPeriod, AcademicYear


# ── AcademicYear ──────────────────────────────────────────────────────────────
def list_years(branch_id):
    return AcademicYear.objects.filter(branch_id=branch_id).order_by("-start_date")


def get_year(branch_id, year_id) -> AcademicYear | None:
    try:
        return AcademicYear.objects.get(branch_id=branch_id, pk=year_id)
    except (AcademicYear.DoesNotExist, ValueError, TypeError):
        return None


def year_name_exists(branch_id, name) -> bool:
    return AcademicYear.objects.filter(branch_id=branch_id, name__iexact=name).exists()


def create_year(branch_id, *, name, start_date, end_date, is_current=False) -> AcademicYear:
    with transaction.atomic():
        if is_current:
            AcademicYear.objects.filter(branch_id=branch_id, is_current=True).update(is_current=False)
        return AcademicYear.objects.create(
            branch_id=branch_id, name=name, start_date=start_date,
            end_date=end_date, is_current=is_current,
        )


def update_year(year: AcademicYear, fields: dict) -> AcademicYear:
    for k, v in fields.items():
        setattr(year, k, v)
    if fields:
        year.save(update_fields=list(fields.keys()))
    return year


def set_current_year(year: AcademicYear) -> AcademicYear:
    """Make this the single current year for its branch (clears the others first)."""
    with transaction.atomic():
        AcademicYear.objects.filter(branch_id=year.branch_id, is_current=True).exclude(
            pk=year.pk
        ).update(is_current=False)
        year.is_current = True
        year.save(update_fields=["is_current"])
    return year


# ── AcademicPeriod ────────────────────────────────────────────────────────────
def list_periods(year_id):
    return AcademicPeriod.objects.filter(academic_year_id=year_id).order_by("sequence")


def get_period(year_id, period_id) -> AcademicPeriod | None:
    try:
        return AcademicPeriod.objects.get(academic_year_id=year_id, pk=period_id)
    except (AcademicPeriod.DoesNotExist, ValueError, TypeError):
        return None


def period_sequence_exists(year_id, sequence) -> bool:
    return AcademicPeriod.objects.filter(academic_year_id=year_id, sequence=sequence).exists()


def create_period(year_id, *, period_type, sequence, name, start_date, end_date) -> AcademicPeriod:
    return AcademicPeriod.objects.create(
        academic_year_id=year_id, period_type=period_type, sequence=sequence,
        name=name, start_date=start_date, end_date=end_date,
    )
