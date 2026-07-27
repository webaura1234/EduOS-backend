"""Album audience / visibility helpers."""

from __future__ import annotations

from rest_framework.exceptions import ValidationError

# Reader-facing audiences that can be combined on an album.
AUDIENCE_STUDENTS = "students"
AUDIENCE_PARENTS = "parents"
AUDIENCE_FACULTY = "faculty"

ALLOWED_AUDIENCES = frozenset({AUDIENCE_STUDENTS, AUDIENCE_PARENTS, AUDIENCE_FACULTY})

_ROLE_TO_AUDIENCE = {
    "student": AUDIENCE_STUDENTS,
    "parent": AUDIENCE_PARENTS,
    "faculty": AUDIENCE_FACULTY,
}


def _legacy_to_list(value: str) -> list[str]:
    if value in ("private", ""):
        return []
    if value == "staff_only":
        return [AUDIENCE_FACULTY]
    if value in ALLOWED_AUDIENCES:
        return [value]
    return [AUDIENCE_STUDENTS]


def normalize_visibility(raw) -> list[str]:
    """Accept a legacy string or a list of audiences; return a deduped list.

    Empty list means private (no reader roles; admins still manage via admin APIs).
    """
    if raw is None:
        return [AUDIENCE_STUDENTS]
    if isinstance(raw, str):
        return _legacy_to_list(raw.strip().lower())
    if isinstance(raw, (list, tuple)):
        if not raw or raw == ["private"]:
            return []
        out: list[str] = []
        for item in raw:
            if not isinstance(item, str):
                raise ValidationError({"visibility": "Each audience must be a string."})
            token = item.strip().lower()
            if token in ("private", ""):
                continue
            if token == "staff_only":
                token = AUDIENCE_FACULTY
            if token not in ALLOWED_AUDIENCES:
                raise ValidationError(
                    {"visibility": f"Invalid audience '{item}'. Use students, parents, and/or faculty."}
                )
            if token not in out:
                out.append(token)
        return out
    raise ValidationError({"visibility": "Visibility must be a list of audiences or a legacy string."})


def visibility_allows(role: str, visibility) -> bool:
    """Whether a portal role may see an album in reader endpoints."""
    if role in ("admin", "super_admin"):
        return True
    audiences = visibility if isinstance(visibility, list) else _legacy_to_list(str(visibility or ""))
    key = _ROLE_TO_AUDIENCE.get(role)
    if key is None:
        return False
    return key in audiences
