"""Admin Attendance overview aggregate — AttendanceData shape."""

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


def test_overview_returns_attendance_data_shape(env):
    resp = _client(env["admin"]).get(reverse("attendance:admin-overview"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    for key in ("live", "rules", "records", "leaveRequests", "auditLog",
                "shortageReport", "detentionList", "monthlyReports"):
        assert key in body, f"missing {key}"
    # live snapshot shape
    assert set(body["live"]) >= {"present", "total", "percent", "classes", "updatedAt"}
    assert body["live"]["percent"] == 0  # no sessions today in a fresh tenant
    # rules come from tenant config defaults
    assert body["rules"]["thresholdPercent"] >= 0
    assert isinstance(body["rules"]["examDayCountsTowardThreshold"], bool)


def test_live_endpoint_returns_snapshot(env):
    resp = _client(env["admin"]).get(reverse("attendance:admin-live"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert set(body) >= {"present", "total", "percent", "classes", "updatedAt"}


def test_overview_requires_admin(env):
    student = UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
                          custom_login_id="STU-1", must_change_password=False)
    resp = _client(student).get(reverse("attendance:admin-overview"))
    assert resp.status_code == 403
