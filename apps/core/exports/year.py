"""Resolve academic year for branch-scoped report exports."""

from __future__ import annotations

from rest_framework.exceptions import ValidationError

from apps.academics.models.calendar import AcademicYear
from apps.academics.queries.calendar import get_current_year, list_years


def resolve_report_year(params: dict | None, branch) -> AcademicYear:
    """Return the AcademicYear for this export.

    Uses ``params["academicYearId"]`` when present; otherwise the branch's
    current year. Raises ValidationError if the id is invalid for the branch
    or no current year exists when the param is omitted.
    """
    params = params or {}
    year_id = params.get("academicYearId") or params.get("academic_year_id")
    if year_id:
        year = AcademicYear.objects.filter(
            pk=year_id, branch_id=branch.pk, is_active=True,
        ).first()
        if year is None:
            raise ValidationError({"academicYearId": "Academic year not found for this branch."})
        return year

    year = get_current_year(branch.pk)
    if year is None:
        raise ValidationError({"academicYearId": "No current academic year is set for this branch."})
    return year


def year_include_inactive(year: AcademicYear) -> bool:
    """Prior/frozen years need inactive enrollments so historical reports stay complete."""
    return not bool(year.is_current)


def definition_requires_academic_year(definition) -> bool:
    return any(getattr(s, "key", None) == "academicYearId" for s in (definition.filters or []))


def apply_default_academic_year(definition, params: dict | None, branch) -> dict:
    """Inject current academicYearId when the definition requires it and params omit it."""
    params = dict(params or {})
    if branch is None or not definition_requires_academic_year(definition):
        return params
    if params.get("academicYearId") or params.get("academic_year_id"):
        return params
    year = resolve_report_year(params, branch)
    params["academicYearId"] = str(year.pk)
    return params


def academic_years_for_catalog(branch) -> list[dict]:
    """Lightweight year list for report catalog metadata."""
    if branch is None:
        return []
    return [
        {
            "id": str(y.pk),
            "name": y.name,
            "isCurrent": bool(y.is_current),
            "startDate": y.start_date.isoformat() if y.start_date else None,
            "endDate": y.end_date.isoformat() if y.end_date else None,
        }
        for y in list_years(branch.pk)
    ]
