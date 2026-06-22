"""Admin Guardian-links overview aggregate."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.guardian import StudentGuardianLink
from apps.accounts.models.profile import GuardianProfile, StudentProfile
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


def test_overview_shape(env):
    resp = _client(env["admin"]).get(reverse("accounts:guardians-overview"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert set(body) == {"links", "students", "guardians"}


def test_link_reflected(env):
    student_user = UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
                               custom_login_id="STU-1", first_name="Riya",
                               must_change_password=False)
    profile = StudentProfile.objects.create(user=student_user)
    parent_user = UserFactory(role=Role.PARENT, tenant=env["tenant"], branch=env["branch"],
                              phone="+919800000000", first_name="Vijay",
                              custom_login_id=None, must_change_password=False)
    GuardianProfile.objects.create(user=parent_user)
    StudentGuardianLink.objects.create(
        student=student_user, guardian=parent_user, relationship="father",
        custody="primary", is_primary_contact=True, has_portal_access=True,
    )

    body = _data(_client(env["admin"]).get(reverse("accounts:guardians-overview")))
    assert len(body["links"]) == 1
    link = body["links"][0]
    assert link["studentName"].startswith("Riya")
    assert link["guardianName"].startswith("Vijay")
    assert link["relationship"] == "father"
    assert link["custodyType"] == "full"   # primary → full
    assert link["isPrimaryContact"] is True
    assert any(g["userId"] == str(parent_user.id) for g in body["guardians"])
    # Student appears in the dropdown list even without an active enrollment.
    assert any(s["studentId"] == str(profile.id) for s in body["students"])


def test_requires_admin(env):
    student = UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
                          custom_login_id="STU-2", must_change_password=False)
    resp = _client(student).get(reverse("accounts:guardians-overview"))
    assert resp.status_code == 403


def _make_student_and_guardian(env, code, phone):
    student_user = UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
                               custom_login_id=code, must_change_password=False)
    profile = StudentProfile.objects.create(user=student_user)
    parent = UserFactory(role=Role.PARENT, tenant=env["tenant"], branch=env["branch"],
                         phone=phone, custom_login_id=None, must_change_password=False)
    GuardianProfile.objects.create(user=parent)
    return profile, parent


def test_save_remove_and_set_primary(env):
    profile, parent = _make_student_and_guardian(env, "STU-G1", "+919800001111")
    parent2 = UserFactory(role=Role.PARENT, tenant=env["tenant"], branch=env["branch"],
                          phone="+919800002222", custom_login_id=None, must_change_password=False)
    GuardianProfile.objects.create(user=parent2)

    url = reverse("accounts:guardians-actions")
    c = _client(env["admin"])

    # Create a link.
    resp = c.post(url, {"action": "save_link", "payload": {
        "studentId": str(profile.id), "guardianUserId": str(parent.id),
        "relationship": "father", "custodyType": "full",
        "hasPortalAccess": True, "isPrimaryContact": True,
    }}, format="json")
    assert resp.status_code == 201, resp.content
    link_id = _data(resp)["id"]

    # Second guardian, set primary → should flip the first off.
    resp = c.post(url, {"action": "save_link", "payload": {
        "studentId": str(profile.id), "guardianUserId": str(parent2.id),
        "relationship": "mother", "custodyType": "shared", "hasPortalAccess": True,
        "isPrimaryContact": False,
    }}, format="json")
    link2_id = _data(resp)["id"]

    resp = c.post(url, {"action": "set_primary", "linkId": link2_id}, format="json")
    assert resp.status_code == 200

    links = {l["id"]: l for l in _data(c.get(reverse("accounts:guardians-overview")))["links"]}
    assert links[link2_id]["isPrimaryContact"] is True
    assert links[link_id]["isPrimaryContact"] is False

    # Remove the first link.
    resp = c.post(url, {"action": "remove_link", "linkId": link_id}, format="json")
    assert resp.status_code == 200
    remaining = {l["id"] for l in _data(c.get(reverse("accounts:guardians-overview")))["links"]}
    assert link_id not in remaining
