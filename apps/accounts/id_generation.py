"""
Unified, per-institution-configurable user ID generation.

`generate_user_id()` is THE single entry point for allocating a student's
admission/roll number or a faculty member's employee ID. Both the invite flow
(`interactors/invite.py`) and the direct create-user flow
(`interactors/user_management.py`) funnel through here, so an institution's
custom_login_id scheme is consistent no matter which door a user is added from.

Format is driven by `organizations.TenantSettings` (student_id_format /
faculty_id_format + widths + yearly-reset). Supported template tokens:

    {BRANCH}  branch code, upper-cased (falls back to "SCH")
    {YEAR}    4-digit academic-year start year, e.g. "2025"
    {YY}      2-digit year, e.g. "25"
    {ROLE}    "STU" for students, "FAC" for faculty
    {SEQ}     zero-padded running sequence (width from settings)

Sequences are gap-free per (branch, purpose, period) via a row-level lock, and
the result is checked against existing IDs so a manually-typed ID that happens to
occupy a slot can never be duplicated.
"""

from __future__ import annotations

from django.db import transaction

from apps.accounts.models.security import IdPurpose
from apps.accounts.models.user import Role

DEFAULT_STUDENT_FORMAT = "{BRANCH}/{YEAR}/{SEQ}"
DEFAULT_FACULTY_FORMAT = "{BRANCH}-FAC-{SEQ}"
DEFAULT_STUDENT_WIDTH = 5
DEFAULT_FACULTY_WIDTH = 4

_MAX_ALLOC_ATTEMPTS = 100


def canonical_year_key(academic_year) -> str:
    """
    Normalise an academic year to the canonical "YYYY-YYYY" key both entry doors
    agree on — so the invite flow (which passes a string) and the create-user flow
    (which passes an AcademicYear row) hit the SAME counter for the same year.

    Accepts an AcademicYear instance, a "2025-2026"/"2025-26" string, or None.
    """
    if academic_year is None:
        return ""
    start_date = getattr(academic_year, "start_date", None)
    if start_date is not None:  # AcademicYear instance
        return f"{start_date.year}-{start_date.year + 1}"
    text = str(academic_year).strip()
    if len(text) >= 4 and text[:4].isdigit():
        start = int(text[:4])
        return f"{start}-{start + 1}"
    return text


def _render(fmt: str, *, branch_code: str, year_key: str, seq: int, width: int, role_token: str) -> str:
    year4 = year_key[:4] if len(year_key) >= 4 and year_key[:4].isdigit() else ""
    yy = year4[2:] if year4 else ""
    return (
        fmt.replace("{BRANCH}", branch_code)
        .replace("{YEAR}", year4)
        .replace("{YY}", yy)
        .replace("{ROLE}", role_token)
        .replace("{SEQ}", str(seq).zfill(max(1, width)))
    )


def _next_sequence(branch, purpose: str, year_key: str) -> int:
    """Atomically increment and return the next sequence for this counter."""
    from apps.accounts.models.security import SequentialIdCounter

    with transaction.atomic():
        counter, _ = SequentialIdCounter.objects.select_for_update().get_or_create(
            branch=branch, purpose=purpose, academic_year=year_key,
            defaults={"last_sequence": 0},
        )
        counter.last_sequence += 1
        counter.save(update_fields=["last_sequence"])
    return counter.last_sequence


def _resolve_config(branch, role: str):
    """Return (fmt, width, purpose, role_token, resets_yearly) for the role."""
    from apps.organizations.queries.institution import get_or_create_tenant_settings

    settings = None
    tenant = getattr(branch, "tenant", None)
    if tenant is not None:
        settings = get_or_create_tenant_settings(tenant)

    if role == Role.FACULTY:
        fmt = (getattr(settings, "faculty_id_format", "") or DEFAULT_FACULTY_FORMAT)
        width = getattr(settings, "faculty_id_seq_width", 0) or DEFAULT_FACULTY_WIDTH
        return fmt, width, IdPurpose.FACULTY, "FAC", False
    fmt = (getattr(settings, "student_id_format", "") or DEFAULT_STUDENT_FORMAT)
    width = getattr(settings, "student_id_seq_width", 0) or DEFAULT_STUDENT_WIDTH
    resets = getattr(settings, "student_id_reset_yearly", True)
    return fmt, width, IdPurpose.STUDENT, "STU", resets


def generate_user_id(branch, role, academic_year=None) -> str:
    """
    Allocate the next custom_login_id for ``role`` at ``branch``.

    Students number per academic year (unless the tenant disables yearly reset);
    faculty number continuously. Guaranteed unique within the tenant.
    """
    fmt, width, purpose, role_token, resets_yearly = _resolve_config(branch, role)
    branch_code = (getattr(branch, "code", "") or "SCH").upper()

    year_key = canonical_year_key(academic_year) if role != Role.FACULTY and resets_yearly else ""

    from apps.admissions.queries.provisioning import custom_login_id_taken

    tenant_id = getattr(branch, "tenant_id", None)
    for _ in range(_MAX_ALLOC_ATTEMPTS):
        seq = _next_sequence(branch, purpose, year_key)
        candidate = _render(
            fmt, branch_code=branch_code, year_key=canonical_year_key(academic_year),
            seq=seq, width=width, role_token=role_token,
        )
        if tenant_id is None or not custom_login_id_taken(tenant_id, candidate):
            return candidate
    raise RuntimeError(
        f"Could not allocate a unique {role} ID for branch {getattr(branch, 'id', '?')} "
        f"after {_MAX_ALLOC_ATTEMPTS} attempts."
    )
