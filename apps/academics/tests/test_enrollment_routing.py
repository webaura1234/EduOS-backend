"""P2.1 — enrollment-based student resolution for exited students."""

import datetime

import pytest

from apps.academics.models import AcademicYear, Batch, Course, Department
from apps.academics.queries import rollover as rol_q
from apps.academics.queries import structure as struct_q
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.admissions.enums import EnrollmentStatus
from apps.admissions.models import StudentEnrollment
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def source_year_scenario():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYear.objects.create(
        branch=branch,
        name="2024-25",
        is_current=True,
        start_date=datetime.date(2024, 6, 1),
        end_date=datetime.date(2025, 4, 30),
    )
    dept = Department.objects.create(branch=branch, name="Science", department_type="stream")
    course = Course.objects.create(department=dept, name="Grade 09")
    batch = Batch.objects.create(course=course, academic_year=year, name="A", capacity=40)
    student = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="STU-P21",
        must_change_password=False,
    )
    profile = StudentProfile.objects.create(
        user=student,
        current_batch=None,
        academic_status=AcademicStatus.ACTIVE,
    )
    enrollment = StudentEnrollment.objects.create(
        branch=branch,
        student_profile=profile,
        batch=batch,
        academic_year=year,
        status=EnrollmentStatus.ACTIVE,
    )
    profile.current_enrollment = enrollment
    profile.save(update_fields=["current_enrollment"])
    return {
        "branch": branch,
        "year": year,
        "batch": batch,
        "profile": profile,
        "enrollment": enrollment,
    }


def test_list_enrollments_in_year_includes_null_current_batch_profile(source_year_scenario):
    scenario = source_year_scenario
    enrollments = list(
        rol_q.list_enrollments_in_year(scenario["branch"].pk, scenario["year"].pk)
    )
    assert scenario["enrollment"] in enrollments
    assert scenario["profile"] in rol_q.list_students_in_year(
        scenario["branch"].pk, scenario["year"].pk
    )


def test_batch_has_students_uses_enrollment_not_profile_batch(source_year_scenario):
    scenario = source_year_scenario
    assert struct_q.batch_has_students(scenario["batch"].pk) is True
