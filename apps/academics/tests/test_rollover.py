"""Validation of academic-year rollover: preview, execute (promotion + freeze), undo,
plus Stage 6 enrollment-aware promotion, graduation, and college arrears (EC-ROL-05)."""

import datetime
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.academics.interactors import rollover as rol_i
from apps.academics.models import AcademicPeriod, AcademicYear, Batch, Course, Department, Subject
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.admissions.models import StudentEnrollment
from apps.examinations.models import Exam, ExamRegistration, MarksEntry
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


# ── Stage 6: enrollment-aware promotion ───────────────────────────────────────
def test_promotion_creates_enrollment(scenario):
    """Promotion now creates a StudentEnrollment for the new year + promoted batch."""
    branch, tenant, student = scenario["branch"], scenario["tenant"], scenario["student"]
    preview = rol_i.build_preview(branch.pk, tenant)
    rol_i.execute_rollover(branch=branch, tenant=tenant, expected_version=preview.version, user=None)

    profile = StudentProfile.objects.get(user=student)
    new_enr = StudentEnrollment.objects.filter(student_profile=profile, is_active=True).first()
    assert new_enr is not None
    assert new_enr.batch.course.name == "Grade 10"
    assert new_enr.academic_year.name == "2025-2026"


def test_undo_soft_deletes_created_enrollment(scenario):
    """EC-ROL-02 — undo soft-deletes the enrollments the run created."""
    branch, tenant, student = scenario["branch"], scenario["tenant"], scenario["student"]
    preview = rol_i.build_preview(branch.pk, tenant)
    rol_i.execute_rollover(branch=branch, tenant=tenant, expected_version=preview.version, user=None)
    profile = StudentProfile.objects.get(user=student)
    assert StudentEnrollment.objects.filter(student_profile=profile, is_active=True).exists()

    rol_i.undo_rollover(branch_id=branch.pk, user=None)
    assert not StudentEnrollment.objects.filter(student_profile=profile, is_active=True).exists()


def test_undo_after_window_expired_blocked(scenario):
    """EC-ROL-04 — undo after the 24h window → 403."""
    from rest_framework.exceptions import PermissionDenied

    from apps.academics.queries import rollover as rol_q

    branch, tenant = scenario["branch"], scenario["tenant"]
    preview = rol_i.build_preview(branch.pk, tenant)
    rol_i.execute_rollover(branch=branch, tenant=tenant, expected_version=preview.version, user=None)

    run = rol_q.get_latest_rollover_run(branch.pk)
    run.undo_expires_at = timezone.now() - datetime.timedelta(hours=1)
    run.save(update_fields=["undo_expires_at"])

    with pytest.raises(PermissionDenied):
        rol_i.undo_rollover(branch_id=branch.pk, user=None)


# ── Stage 6: college graduation + arrears (EC-ROL-05) ─────────────────────────
@pytest.fixture
def college_scenario():
    """A college with one (final-year) course and a student enrolled in it."""
    tenant = TenantFactory(institution_type="college")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYear.objects.create(
        branch=branch, name="2024-25", is_current=True,
        start_date=datetime.date(2024, 6, 1), end_date=datetime.date(2025, 4, 30),
    )
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type="semester", sequence=1, name="Sem 1",
        start_date=datetime.date(2024, 6, 1), end_date=datetime.date(2024, 10, 31),
    )
    dept = Department.objects.create(branch=branch, name="CS", department_type="department")
    course = Course.objects.create(department=dept, name="Final Year")  # only course → final
    batch = Batch.objects.create(course=course, academic_year=year, name="A", capacity=40)
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                          custom_login_id="STU-C1", must_change_password=False)
    profile = StudentProfile.objects.create(
        user=student, current_batch=batch, academic_status=AcademicStatus.ACTIVE
    )
    enrollment = StudentEnrollment.objects.create(
        branch=branch, student_profile=profile, batch=batch, academic_year=year
    )
    return {"tenant": tenant, "branch": branch, "year": year, "period": period,
            "course": course, "batch": batch, "student": student, "profile": profile,
            "enrollment": enrollment}


def test_final_year_no_arrears_graduates(college_scenario):
    """EC-ROL-03 — a final-year student with no backlog graduates."""
    cs = college_scenario
    preview = rol_i.build_preview(cs["branch"].pk, cs["tenant"])
    rol_i.execute_rollover(branch=cs["branch"], tenant=cs["tenant"],
                           expected_version=preview.version, user=None)
    profile = StudentProfile.objects.get(user=cs["student"])
    assert profile.academic_status == AcademicStatus.GRADUATED
    assert profile.current_batch_id is None


def test_college_arrears_carried_on_rollover(college_scenario):
    """EC-ROL-05 — final-year with open arrears is retained, backlog carried, regs intact."""
    cs = college_scenario
    exam = Exam.objects.create(branch=cs["branch"], academic_period=cs["period"],
                               name="Finals", exam_type="final", is_published=True)
    maths = Subject.objects.create(course=cs["course"], name="Maths", code="M1",
                                   pass_marks=35, max_marks=100)
    physics = Subject.objects.create(course=cs["course"], name="Physics", code="P1",
                                     pass_marks=35, max_marks=100)
    for subj in (maths, physics):
        MarksEntry.objects.create(exam=exam, subject=subj, student=cs["enrollment"],
                                  marks=Decimal("20"), marks_status="submitted")
    reg = ExamRegistration.objects.create(exam=exam, student=cs["enrollment"], is_arrear=True)

    preview = rol_i.build_preview(cs["branch"].pk, cs["tenant"])
    rol_i.execute_rollover(branch=cs["branch"], tenant=cs["tenant"],
                           expected_version=preview.version, user=None)

    profile = StudentProfile.objects.get(user=cs["student"])
    # Not graduated — retained with arrears.
    assert profile.academic_status == AcademicStatus.ACTIVE
    # New enrollment in the new year carrying both arrear subjects.
    new_enr = StudentEnrollment.objects.filter(
        student_profile=profile, academic_year__name="2025-2026", is_active=True
    ).first()
    assert new_enr is not None
    assert len(new_enr.backlog_subjects) == 2
    # Original arrear registration left intact (not archived).
    reg.refresh_from_db()
    assert reg.is_active is True
    # Student exam hub surfaces 2 pending arrears.
    from apps.examinations.interactors.hub import build_exam_hub
    hub = build_exam_hub(profile, tenant=cs["tenant"])
    assert len(hub["pendingArrears"]) == 2
    assert all(a["status"] == "pending_arrear" for a in hub["pendingArrears"])
