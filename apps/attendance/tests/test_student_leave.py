"""Student-facing leave endpoint (my requests + self-apply)."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.tests.factories import StudentEnrollmentFactory
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
def student_env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    user = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                       custom_login_id="STU-1", first_name="Polo",
                       must_change_password=False)
    profile = StudentProfile.objects.create(user=user, current_batch=batch)
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)
    return dict(branch=branch, user=user, profile=profile)


def test_apply_then_list_own_leave(student_env):
    c = _client(student_env["user"])
    url = reverse("attendance:student-leave")

    resp = c.post(url, {"fromDate": "2026-07-01", "toDate": "2026-07-03",
                        "reason": "Family function"}, format="json")
    assert resp.status_code == 201, resp.content
    leave = _data(resp)["leave"]
    assert leave["status"] == "pending"
    assert leave["appliedByRole"] == "student"

    resp = c.get(url)
    assert resp.status_code == 200, resp.content
    reqs = _data(resp)["requests"]
    assert len(reqs) == 1
    assert reqs[0]["reason"] == "Family function"


def test_list_empty_without_enrollment(student_env):
    # A different student with no enrollment.
    other = UserFactory(role=Role.STUDENT, tenant=student_env["branch"].tenant,
                        branch=student_env["branch"], custom_login_id="STU-X",
                        must_change_password=False)
    StudentProfile.objects.create(user=other)
    resp = _client(other).get(reverse("attendance:student-leave"))
    assert resp.status_code == 200, resp.content
    assert _data(resp)["requests"] == []
