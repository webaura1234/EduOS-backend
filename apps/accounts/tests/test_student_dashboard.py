"""Student dashboard aggregate."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.tests.factories import StudentEnrollmentFactory
from apps.fees.models.invoice import FeeInvoice
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
    user = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                       custom_login_id="STU-1", first_name="Polo", must_change_password=False)
    profile = StudentProfile.objects.create(user=user, current_batch=batch)
    enrollment = StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)
    return dict(branch=branch, user=user, profile=profile, enrollment=enrollment, batch=batch)


def test_dashboard_shape(env):
    resp = _client(env["user"]).get(reverse("accounts:student-dashboard"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    for key in ("institutionType", "profile", "attendancePercent", "attendanceThreshold",
                "attendanceAlert", "feeAlert", "scheduleToday", "upcomingExamsCount",
                "nextExamLabel", "hallTicketAvailable", "announcements"):
        assert key in body, f"missing {key}"
    assert body["profile"]["name"].startswith("Polo")
    # classLabel now shows class + section, e.g. "Course X - Section Y".
    assert body["profile"]["classLabel"] == f"{env['batch'].course.name} - {env['batch'].name}"
    assert body["profile"]["sectionName"] == env["batch"].name
    assert body["profile"]["className"] == env["batch"].course.name


def test_dashboard_fee_alert(env):
    FeeInvoice.objects.create(branch=env["branch"], student=env["enrollment"],
                              total_paise=1120000, paid_paise=0)
    body = _data(_client(env["user"]).get(reverse("accounts:student-dashboard")))
    assert body["feeAlert"] is not None
    assert body["feeAlert"]["amountDue"] == 11200.0


def test_dashboard_requires_student(env):
    admin = UserFactory(role=Role.ADMIN, tenant=env["branch"].tenant, branch=env["branch"],
                        phone="+919810000099", custom_login_id=None, must_change_password=False)
    resp = _client(admin).get(reverse("accounts:student-dashboard"))
    assert resp.status_code == 403
