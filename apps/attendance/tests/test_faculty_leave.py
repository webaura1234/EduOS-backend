"""Faculty leave-review queue (pending/decided student leaves)."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.tests.factories import StudentEnrollmentFactory
from apps.attendance.models import LeaveRequest
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                          custom_login_id="FAC-1", must_change_password=False)
    su = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                     custom_login_id="STU-1", first_name="Ravi", must_change_password=False)
    profile = StudentProfile.objects.create(user=su, current_batch=batch)
    enrollment = StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)
    return dict(branch=branch, faculty=faculty, enrollment=enrollment, applied_by=su)


def test_pending_and_decided_split(env):
    LeaveRequest.objects.create(
        branch=env["branch"], applicant_role="student", student=env["enrollment"],
        applied_by=env["applied_by"], from_date=datetime.date(2026, 7, 1),
        to_date=datetime.date(2026, 7, 2), reason="Trip", status="pending",
    )
    LeaveRequest.objects.create(
        branch=env["branch"], applicant_role="student", student=env["enrollment"],
        applied_by=env["applied_by"], from_date=datetime.date(2026, 6, 1),
        to_date=datetime.date(2026, 6, 2), reason="Sick", status="approved",
    )
    body = _data(_client(env["faculty"]).get(reverse("attendance:faculty-leave-review")))
    assert len(body["pending"]) == 1
    assert len(body["decided"]) == 1
    assert body["pending"][0]["reason"] == "Trip"
    assert body["pending"][0]["studentName"].startswith("Ravi")


def test_requires_faculty(env):
    resp = _client(env["applied_by"]).get(reverse("attendance:faculty-leave-review"))
    assert resp.status_code == 403
