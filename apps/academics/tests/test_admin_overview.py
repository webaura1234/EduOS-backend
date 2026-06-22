"""Admin Academics overview aggregate — AcademicsData shape."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
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
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch,
                        phone="+919810000001", custom_login_id=None,
                        must_change_password=False)
    return dict(tenant=tenant, branch=branch, admin=admin)


def test_overview_returns_academics_data_shape(env):
    resp = _client(env["admin"]).get(reverse("academics:admin-overview"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    for key in ("institutionType", "hierarchyLabel", "periodKind", "academicYears",
                "periods", "holidays", "workingDays", "departments", "classSections",
                "subjects", "rooms", "timetableSlots", "substitutions", "studyMaterials",
                "faculty", "adminReviewQueue", "calendarChanges", "attendanceFrozenThrough"):
        assert key in body, f"missing {key}"


def test_school_labels_and_working_days(env):
    body = _data(_client(env["admin"]).get(reverse("academics:admin-overview")))
    assert body["institutionType"] == "school"
    assert body["hierarchyLabel"] == "Stream"
    assert body["periodKind"] == "term"
    assert len(body["workingDays"]) == 7
    sunday = next(d for d in body["workingDays"] if d["dayOfWeek"] == 0)
    assert sunday["isWorkingDay"] is False


def test_college_labels(env):
    env["tenant"].institution_type = "college"
    env["tenant"].save(update_fields=["institution_type"])
    body = _data(_client(env["admin"]).get(reverse("academics:admin-overview")))
    assert body["hierarchyLabel"] == "Department"
    assert body["periodKind"] == "semester"


def test_faculty_listed(env):
    UserFactory(role=Role.FACULTY, tenant=env["tenant"], branch=env["branch"],
                custom_login_id="FAC-1", first_name="Asha", must_change_password=False)
    body = _data(_client(env["admin"]).get(reverse("academics:admin-overview")))
    assert any(f["name"].startswith("Asha") for f in body["faculty"])


def test_requires_admin(env):
    student = UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
                          custom_login_id="STU-1", must_change_password=False)
    resp = _client(student).get(reverse("academics:admin-overview"))
    assert resp.status_code == 403
