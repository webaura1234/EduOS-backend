"""Announcements — admin create/list + student feed visibility."""

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
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch,
                        phone="+919810000001", custom_login_id=None, must_change_password=False)
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                          custom_login_id="STU-1", must_change_password=False)
    profile = StudentProfile.objects.create(user=student, current_batch=batch)
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)
    return dict(branch=branch, admin=admin, student=student, batch=batch)


def test_admin_create_and_list(env):
    url = reverse("communications:announcements")
    resp = _client(env["admin"]).post(url, {
        "title": "Parking update", "body": "Use Gate B",
        "targetType": "all", "channels": ["in_app", "sms"],
    }, format="json")
    assert resp.status_code == 201, resp.content
    a = _data(resp)["announcement"]
    assert a["title"] == "Parking update"
    assert a["deliveryStatus"]["in_app"] == "sent"
    assert a["deliveryStatus"]["email"] == "skipped"

    rows = _data(_client(env["admin"]).get(url))["announcements"]
    assert len(rows) == 1


def test_student_sees_all_and_role_targeted(env):
    admin = _client(env["admin"])
    url = reverse("communications:announcements")
    admin.post(url, {"title": "Everyone notice", "body": "x", "targetType": "all",
                     "channels": ["in_app"]}, format="json")
    admin.post(url, {"title": "Staff only", "body": "y", "targetType": "role",
                     "targetValue": "faculty", "channels": ["in_app"]}, format="json")

    feed = _data(_client(env["student"]).get(reverse("communications:student-announcements")))
    titles = {a["title"] for a in feed["announcements"]}
    assert "Everyone notice" in titles
    assert "Staff only" not in titles  # role=faculty hidden from student


def test_faculty_feed(env):
    admin = _client(env["admin"])
    url = reverse("communications:announcements")
    admin.post(url, {"title": "All-staff notice", "body": "x", "targetType": "all",
                     "channels": ["in_app"]}, format="json")
    admin.post(url, {"title": "Faculty meeting", "body": "y", "targetType": "role",
                     "targetValue": "faculty", "channels": ["in_app"]}, format="json")
    admin.post(url, {"title": "Students only", "body": "z", "targetType": "role",
                     "targetValue": "student", "channels": ["in_app"]}, format="json")

    faculty = UserFactory(role=Role.FACULTY, tenant=env["branch"].tenant, branch=env["branch"],
                          custom_login_id="FAC-1", must_change_password=False)
    feed = _data(_client(faculty).get(reverse("communications:faculty-announcements")))
    titles = {a["title"] for a in feed["announcements"]}
    assert "All-staff notice" in titles
    assert "Faculty meeting" in titles
    assert "Students only" not in titles


def test_validation(env):
    resp = _client(env["admin"]).post(reverse("communications:announcements"),
                                      {"title": "", "body": ""}, format="json")
    assert resp.status_code == 400
