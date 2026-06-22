"""Homework — faculty assign/list + student published feed."""

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
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                          custom_login_id="FAC-1", must_change_password=False)
    su = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                     custom_login_id="STU-1", must_change_password=False)
    profile = StudentProfile.objects.create(user=su, current_batch=batch)
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)
    return dict(branch=branch, batch=batch, faculty=faculty, student=su)


def test_faculty_assign_and_list_homework(env):
    url = reverse("coursework:faculty-homework")
    resp = _client(env["faculty"]).post(url, {
        "classSectionId": str(env["batch"].id), "date": "2026-06-22",
        "title": "Read chapter 4", "details": "Pages 40-55", "publish": True,
    }, format="json")
    assert resp.status_code == 201, resp.content
    entry = _data(resp)["entry"]
    assert entry["status"] == "published" and entry["classLabel"]

    body = _data(_client(env["faculty"]).get(url))
    assert body["canAssign"] is True
    assert any(c["id"] == str(env["batch"].id) for c in body["classes"])
    assert len(body["homework"]) == 1


def test_student_sees_only_published_for_their_batch(env):
    url = reverse("coursework:faculty-homework")
    fc = _client(env["faculty"])
    fc.post(url, {"classSectionId": str(env["batch"].id), "date": "2026-06-22",
                  "title": "Published", "publish": True}, format="json")
    fc.post(url, {"classSectionId": str(env["batch"].id), "date": "2026-06-22",
                  "title": "Draft", "publish": False}, format="json")

    body = _data(_client(env["student"]).get(reverse("coursework:student-homework")))
    titles = [h["title"] for h in body["homework"]]
    assert titles == ["Published"]


def test_edit_existing_homework(env):
    url = reverse("coursework:faculty-homework")
    fc = _client(env["faculty"])
    created = _data(fc.post(url, {"classSectionId": str(env["batch"].id),
                                  "date": "2026-06-22", "title": "Old",
                                  "publish": False}, format="json"))["entry"]
    edited = _data(fc.post(url, {"id": created["id"], "classSectionId": str(env["batch"].id),
                                 "date": "2026-06-22", "title": "New",
                                 "publish": True}, format="json"))["entry"]
    assert edited["id"] == created["id"]
    assert edited["title"] == "New" and edited["status"] == "published"
