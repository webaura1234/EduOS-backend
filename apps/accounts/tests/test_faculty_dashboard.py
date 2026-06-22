"""Faculty dashboard aggregate."""

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
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                          custom_login_id="FAC-1", first_name="Asha", must_change_password=False)
    return dict(branch=branch, faculty=faculty)


def test_dashboard_shape(env):
    resp = _client(env["faculty"]).get(reverse("accounts:faculty-dashboard"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    for key in ("today", "schedule", "snapshot", "quickActions", "alerts",
                "cards", "announcements", "upcomingHolidays"):
        assert key in body, f"missing {key}"
    assert set(body["snapshot"]) == {
        "sessionsToday", "sessionsCompleted", "pendingLeave", "announcementsCount",
        "attendanceMarkedPercent", "syllabusProgressPercent",
    }
    assert isinstance(body["schedule"], list)
    assert len(body["quickActions"]) == 3


def test_dashboard_requires_faculty(env):
    student = UserFactory(role=Role.STUDENT, tenant=env["branch"].tenant, branch=env["branch"],
                          custom_login_id="STU-1", must_change_password=False)
    resp = _client(student).get(reverse("accounts:faculty-dashboard"))
    assert resp.status_code == 403
