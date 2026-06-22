"""Grievances module — student raise/list + admin inbox/assign/resolve."""

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
                        phone="+919810000001", custom_login_id=None, must_change_password=False)
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                          custom_login_id="STU-1", first_name="Polo", must_change_password=False)
    return dict(tenant=tenant, branch=branch, admin=admin, student=student)


def test_student_raise_and_list(env):
    url = reverse("grievances:student-grievances")
    c = _client(env["student"])

    resp = c.post(url, {"category": "Transport", "subject": "Bus late",
                        "description": "Bus is late daily"}, format="json")
    assert resp.status_code == 201, resp.content
    g = _data(resp)["grievance"]
    assert g["status"] == "open"
    assert g["raisedByRole"] == "student"

    resp = c.get(url)
    assert resp.status_code == 200, resp.content
    grievances = _data(resp)["grievances"]
    assert len(grievances) == 1
    assert grievances[0]["subject"] == "Bus late"


def test_student_validation(env):
    resp = _client(env["student"]).post(
        reverse("grievances:student-grievances"),
        {"category": "", "subject": ""}, format="json",
    )
    assert resp.status_code == 400


def test_admin_inbox_and_resolve(env):
    # Student raises one.
    _client(env["student"]).post(
        reverse("grievances:student-grievances"),
        {"category": "Fees", "subject": "Wrong amount", "description": "x"}, format="json",
    )
    admin = _client(env["admin"])

    resp = admin.get(reverse("grievances:admin-grievances"))
    assert resp.status_code == 200, resp.content
    rows = _data(resp)["grievances"]
    assert len(rows) == 1
    gid = rows[0]["id"]
    assert rows[0]["raisedByName"].startswith("Polo")

    # Assign then resolve.
    resp = admin.post(reverse("grievances:admin-actions"),
                      {"action": "assign", "grievanceId": gid,
                       "assigneeId": str(env["admin"].id)}, format="json")
    assert resp.status_code == 200, resp.content
    assert _data(resp)["grievance"]["status"] == "in_review"

    resp = admin.post(reverse("grievances:admin-actions"),
                      {"action": "resolve", "grievanceId": gid,
                       "resolutionNote": "Fixed", "status": "resolved"}, format="json")
    assert resp.status_code == 200, resp.content
    g = _data(resp)["grievance"]
    assert g["status"] == "resolved"
    assert g["resolutionNote"] == "Fixed"


def test_student_cannot_access_admin_inbox(env):
    resp = _client(env["student"]).get(reverse("grievances:admin-grievances"))
    assert resp.status_code == 403
