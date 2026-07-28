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

        if spec.type == "select" and spec.options:
            allowed = {str(o.get("value")) for o in spec.options}
            if str(value) not in allowed:
                errors[spec.key] = f"{spec.label} must be one of: {', '.join(sorted(allowed))}."
                continue

        if spec.type in ("number", "batch_id", "exam_id") and not _is_numeric(value):
            if spec.type in ("batch_id", "exam_id") and _is_uuid(value):
                pass
            else:
                errors[spec.key] = f"{spec.label} must be a number."
                continue

        if spec.type == "academic_year_id" and not (_is_uuid(value) or _is_numeric(value)):
            errors[spec.key] = f"{spec.label} must be a valid id."
            continue

        if spec.type == "date" and not _is_date(value):
            errors[spec.key] = f"{spec.label} must be a valid date (YYYY-MM-DD)."
            continue

        if spec.type == "date_range":
            normalized, err = _normalize_date_range(value)
            if err:
                errors[spec.key] = f"{spec.label} {err}"
                continue
            params[spec.key] = normalized
            continue

        if spec.type == "number":
            params[spec.key] = int(value)

    if errors:
        raise ValidationError(errors)
    return params


def _normalize_date_range(value):
    """Accept {from,to} / {fromDate,toDate} dict or skip empty halves."""
    if isinstance(value, dict):
        start = value.get("from") or value.get("fromDate") or value.get("start")
        end = value.get("to") or value.get("toDate") or value.get("end")
    else:
        return None, "must be an object with from/to dates."
    if start in (None, "") and end in (None, ""):
        return None, None
    if start and not _is_date(start):
        return None, "from must be a valid date (YYYY-MM-DD)."
    if end and not _is_date(end):
        return None, "to must be a valid date (YYYY-MM-DD)."
    return {"from": start or None, "to": end or None}, None


def _is_numeric(value) -> bool:
    try:
        int(value)
        return True
    except (TypeError, ValueError):
        return False


def _is_uuid(value) -> bool:
    import uuid
    try:
        uuid.UUID(str(value))
        return True
    except (TypeError, ValueError, AttributeError):
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
            "options": s.options,
            "group": s.group,
        }
        for s in specs
    ]
