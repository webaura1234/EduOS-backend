"""Tests for the unified, per-institution-configurable ID generator."""

import pytest

from apps.accounts.id_generation import canonical_year_key, generate_user_id
from apps.accounts.models.user import Role
from apps.organizations.queries.institution import get_or_create_tenant_settings
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _branch(code="ABCS"):
    tenant = TenantFactory()
    return BranchFactory(tenant=tenant, code=code)


def test_student_id_uses_default_format_and_pads_sequence():
    branch = _branch("ABCS")
    first = generate_user_id(branch, Role.STUDENT, "2025-2026")
    second = generate_user_id(branch, Role.STUDENT, "2025-2026")
    assert first == "ABCS/2025/00001"
    assert second == "ABCS/2025/00002"


def test_faculty_id_runs_continuously_across_years():
    branch = _branch("ABCS")
    a = generate_user_id(branch, Role.FACULTY)
    b = generate_user_id(branch, Role.FACULTY)
    assert a == "ABCS-FAC-0001"
    assert b == "ABCS-FAC-0002"


def test_student_sequence_resets_per_academic_year():
    branch = _branch("ABCS")
    y1 = generate_user_id(branch, Role.STUDENT, "2025-2026")
    y2 = generate_user_id(branch, Role.STUDENT, "2026-2027")
    assert y1 == "ABCS/2025/00001"
    assert y2 == "ABCS/2026/00001"


def test_both_entry_doors_share_one_counter():
    """A string year and an equivalent AcademicYear must hit the same counter."""

    class _FakeYear:
        class _D:
            year = 2025

        start_date = _D()

    branch = _branch("ABCS")
    from_string = generate_user_id(branch, Role.STUDENT, "2025-2026")
    from_object = generate_user_id(branch, Role.STUDENT, _FakeYear())
    assert from_string == "ABCS/2025/00001"
    assert from_object == "ABCS/2025/00002"  # continues, not a reset


def test_custom_format_and_width_from_settings():
    branch = _branch("CMR")
    settings = get_or_create_tenant_settings(branch.tenant)
    settings.student_id_format = "{PREFIX}{YY}-{SEQ}".replace("{PREFIX}", "ADM")
    settings.student_id_seq_width = 3
    settings.save(update_fields=["student_id_format", "student_id_seq_width"])

    got = generate_user_id(branch, Role.STUDENT, "2025-2026")
    assert got == "ADM25-001"


def test_no_yearly_reset_keeps_running():
    branch = _branch("ABCS")
    settings = get_or_create_tenant_settings(branch.tenant)
    settings.student_id_reset_yearly = False
    settings.save(update_fields=["student_id_reset_yearly"])

    y1 = generate_user_id(branch, Role.STUDENT, "2025-2026")
    y2 = generate_user_id(branch, Role.STUDENT, "2026-2027")
    assert y1.endswith("00001")
    assert y2.endswith("00002")  # did not reset


def test_canonical_year_key_normalises_variants():
    assert canonical_year_key("2025-2026") == "2025-2026"
    assert canonical_year_key("2025-26") == "2025-2026"
    assert canonical_year_key(None) == ""
