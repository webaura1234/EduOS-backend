"""Interactors — configurable enquiry form: fetch, save, and validate submissions."""

from __future__ import annotations

import re
from datetime import datetime

from django.utils.text import slugify
from rest_framework.exceptions import ValidationError

from apps.admissions.models.enquiry_form import EnquiryFieldType, EnquiryForm

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^[+()\-\s0-9]{6,20}$")


def get_or_create_form(branch) -> EnquiryForm:
    form, _ = EnquiryForm.objects.get_or_create(branch=branch)
    return form


def _normalise_keys(fields: list[dict]) -> list[dict]:
    """Assign stable, unique slug keys, deriving from the label when missing."""
    used: set[str] = set()
    out: list[dict] = []
    for idx, field in enumerate(fields):
        key = (field.get("key") or "").strip() or slugify(field["label"])[:50]
        key = key or f"field_{idx + 1}"
        base, n = key, 2
        while key in used:
            key = f"{base}_{n}"
            n += 1
        used.add(key)
        out.append({
            "key": key,
            "label": field["label"].strip(),
            "type": field["type"],
            "required": bool(field.get("required", False)),
            "options": field.get("options", []),
            "placeholder": field.get("placeholder", ""),
        })
    return out


def save_form(branch, *, title: str, description: str, is_public: bool, fields: list[dict]) -> EnquiryForm:
    form = get_or_create_form(branch)
    form.title = title.strip() or "Admission Enquiry"
    form.description = description.strip()
    form.is_public = is_public
    form.fields = _normalise_keys(fields)
    form.save(update_fields=["title", "description", "is_public", "fields", "updated_at"])
    return form


def _coerce_value(field: dict, raw):
    """Validate + normalise one answer; raise ValidationError keyed by field key."""
    key, label, ftype = field["key"], field["label"], field["type"]
    is_empty = raw is None or (isinstance(raw, str) and not raw.strip())

    if is_empty:
        if field.get("required"):
            raise ValidationError({key: f"{label} is required."})
        return None

    if ftype == EnquiryFieldType.CHECKBOX:
        return bool(raw) and str(raw).lower() not in {"false", "0", "no"}

    value = str(raw).strip()

    if ftype == EnquiryFieldType.EMAIL and not _EMAIL_RE.match(value):
        raise ValidationError({key: f"{label} must be a valid email."})
    if ftype == EnquiryFieldType.PHONE and not _PHONE_RE.match(value):
        raise ValidationError({key: f"{label} must be a valid phone number."})
    if ftype == EnquiryFieldType.NUMBER:
        try:
            float(value)
        except ValueError:
            raise ValidationError({key: f"{label} must be a number."})
    if ftype == EnquiryFieldType.DATE:
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValidationError({key: f"{label} must be a valid date (YYYY-MM-DD)."})
    if ftype == EnquiryFieldType.SELECT and value not in (field.get("options") or []):
        raise ValidationError({key: f"{label}: '{value}' is not a valid choice."})

    return value


def validate_submission(form: EnquiryForm, answers: dict) -> dict:
    """
    Validate a raw {key: value} answer map against the form schema.
    Returns the cleaned custom_fields dict (only known, non-empty fields).
    """
    answers = answers or {}
    cleaned: dict = {}
    for field in form.fields or []:
        value = _coerce_value(field, answers.get(field["key"]))
        if value is not None:
            cleaned[field["key"]] = value
    return cleaned
