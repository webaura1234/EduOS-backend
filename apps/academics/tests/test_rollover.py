"""Validation of academic-year rollover: preview, execute (promotion + freeze), undo."""

import datetime

import pytest

from apps.academics.interactors import rollover as rol_i
from apps.academics.models import AcademicPeriod, AcademicYear, Batch, Course, Department
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def scenario():
    """A school with year 2024-25 (current), Grade 09 → Grade 10, and one student in 9-A."""
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYear.objects.create(
        branch=branch, name="2024-25", is_current=True,
        start_date=datetime.date(2024, 6, 1), end_date=datetime.date(2025, 4, 30),
    )
    AcademicPeriod.objects.create(
        academic_year=year, period_type="term", sequence=1, name="Term 1",
        start_date=datetime.date(2024, 6, 1), end_date=datetime.date(2024, 10, 31),
    )
    dept = Department.objects.create(branch=branch, name="Science", department_type="stream")
    c9 = Course.objects.create(department=dept, name="Grade 09")
    Course.objects.create(department=dept, name="Grade 10")
    batch9 = Batch.objects.create(course=c9, academic_year=year, name="A", capacity=40)

    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                          custom_login_id="STU-R1", must_change_password=False)
    StudentProfile.objects.create(user=student, current_batch=batch9, academic_status=AcademicStatus.ACTIVE)

    return {"tenant": tenant, "branch": branch, "year": year, "batch9": batch9, "student": student}


def test_preview_lists_promotion(scenario):
    preview = rol_i.build_preview(scenario["branch"].pk, scenario["tenant"])
    assert preview.from_year_label == "2024-25"
    assert preview.to_year_label == "2025-2026"  # generator expands the suffix
    assert len(preview.students_to_promote) == 1
    row = preview.students_to_promote[0]
    assert row.from_class == "Grade 09 — A"
    assert row.to_class == "Grade 10 — A"


def test_execute_promotes_and_freezes(scenario):
    branch, tenant, student = scenario["branch"], scenario["tenant"], scenario["student"]
    preview = rol_i.build_preview(branch.pk, tenant)

    result = rol_i.execute_rollover(
        branch=branch, tenant=tenant, expected_version=preview.version, user=None,
    )
    assert result["status"] == "succeeded"

    # Old year frozen and no longer current; exactly one current year (the new one).
    scenario["year"].refresh_from_db()
    assert scenario["year"].is_frozen is True
    assert scenario["year"].is_current is False
    current = AcademicYear.objects.filter(branch=branch, is_current=True)
    assert current.count() == 1 and current.first().name == "2025-2026"

    # Student promoted into a Grade 10 batch in the new year.
    profile = StudentProfile.objects.get(user=student)
    assert profile.current_batch.course.name == "Grade 10"
    assert profile.current_batch.academic_year.name == "2025-2026"


def test_execute_rejects_stale_version(scenario):
    from rest_framework.exceptions import ValidationError

    with pytest.raises(ValidationError):
        rol_i.execute_rollover(
            branch=scenario["branch"], tenant=scenario["tenant"], expected_version=999, user=None,
        )


def test_undo_restores_previous_state(scenario):
    branch, tenant, student = scenario["branch"], scenario["tenant"], scenario["student"]
    preview = rol_i.build_preview(branch.pk, tenant)
    rol_i.execute_rollover(branch=branch, tenant=tenant, expected_version=preview.version, user=None)

    # Sanity: status says undo is available.
    status = rol_i.get_rollover_status(branch.pk)
    assert status["canUndo"] is True

    rol_i.undo_rollover(branch_id=branch.pk, user=None)

    # Student is back in the original 9-A batch.
    profile = StudentProfile.objects.get(user=student)
    assert profile.current_batch_id == scenario["batch9"].pk
    assert profile.academic_status == AcademicStatus.ACTIVE

    # Old year is current + unfrozen again; new year is no longer active/current.
    scenario["year"].refresh_from_db()
    assert scenario["year"].is_current is True
    assert scenario["year"].is_frozen is False
    # Exactly one current year survives (validates the unique-current-year fix).
    assert AcademicYear.objects.filter(branch=branch, is_current=True).count() == 1
    assert AcademicYear.objects.filter(branch=branch, name="2025-2026", is_active=True).count() == 0
