"""Report parameter validation against FilterSpec metadata."""

from rest_framework.exceptions import ValidationError

from apps.core.exports.base import ExportDefinition, FilterSpec


def validate_params(definition: ExportDefinition, params: dict) -> dict:
    """Validate and normalize params against definition.filters; return cleaned dict."""
    params = dict(params or {})
    errors = {}

    for spec in definition.filters:
        value = params.get(spec.key)
        if spec.required and (value is None or value == ""):
            errors[spec.key] = f"{spec.label} is required."
            continue
        if value is None or value == "":
            continue
        if spec.type in ("number", "batch_id", "exam_id") and not _is_numeric(value):
            errors[spec.key] = f"{spec.label} must be a number."
        if spec.type == "date" and not _is_date(value):
            errors[spec.key] = f"{spec.label} must be a valid date (YYYY-MM-DD)."

    if errors:
        raise ValidationError(errors)
    return params


def _is_numeric(value) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def _is_date(value) -> bool:
    import datetime
    if isinstance(value, datetime.date):
        return True
    try:
        datetime.date.fromisoformat(str(value))
        return True
    except ValueError:
        return False


def filter_specs_to_dict(specs: list[FilterSpec]) -> list[dict]:
    return [
        {
            "key": s.key,
            "label": s.label,
            "type": s.type,
            "required": s.required,
            "optionsSource": s.options_source,
        }
        for s in specs
    ]
