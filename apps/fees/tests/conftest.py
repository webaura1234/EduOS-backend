"""Shared pytest fixtures for the fees app tests."""

import datetime
import pytest
from rest_framework.test import APIClient

from apps.academics.models import AcademicYear, Batch, Course, Department
from apps.accounts.models import GuardianProfile, StudentProfile
from apps.accounts.models.guardian import StudentGuardianLink
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.organizations.tests.factories import BranchFactory, TenantFactory


@pytest.fixture
def tenant():
    return TenantFactory(institution_type="school")


@pytest.fixture
def branch(tenant):
    return BranchFactory(tenant=tenant)


@pytest.fixture
def admin(tenant, branch):
    return UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919800000001",
        custom_login_id=None,
        must_change_password=False,
    )


@pytest.fixture
def student_user(tenant, branch):
    return UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="STU-001",
        must_change_password=False,
    )


@pytest.fixture
def student_profile(student_user, batch):
    from apps.accounts.models.profile import AcademicStatus
    return StudentProfile.objects.create(
        user=student_user,
        current_batch=batch,
        academic_status=AcademicStatus.ACTIVE,
    )


@pytest.fixture
def parent_user(tenant, branch):
    return UserFactory(
        role=Role.PARENT,
        tenant=tenant,
        branch=branch,
        phone="+919800000002",
        custom_login_id=None,
        must_change_password=False,
    )


@pytest.fixture
def guardian_profile(parent_user):
    return GuardianProfile.objects.create(
        user=parent_user,
        relationship_default="father",
    )


@pytest.fixture
def guardian_link(student_user, parent_user, guardian_profile):
    return StudentGuardianLink.objects.create(
        student=student_user,
        guardian=parent_user,
        relationship="father",
        has_portal_access=True,
    )


@pytest.fixture
def academic_year(branch):
    return AcademicYear.objects.create(
        branch=branch,
        name="2024-25",
        is_current=True,
        start_date=datetime.date(2024, 6, 1),
        end_date=datetime.date(2025, 4, 30),
    )


@pytest.fixture
def department(branch):
    return Department.objects.create(
        branch=branch,
        name="High School",
        department_type="academic",
    )


@pytest.fixture
def course(department):
    return Course.objects.create(
        department=department,
        name="Class 10",
    )


@pytest.fixture
def batch(course, academic_year):
    return Batch.objects.create(
        course=course,
        academic_year=academic_year,
        name="Section A",
    )


@pytest.fixture
def admin_client(admin):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(admin)}")
    return c


@pytest.fixture
def student_client(student_user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(student_user)}")
    return c


@pytest.fixture
def parent_client(parent_user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(parent_user)}")
    return c
