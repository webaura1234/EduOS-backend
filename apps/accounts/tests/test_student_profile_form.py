"""Student account Profile tab — view form, edit name/ownPhone, change password."""

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
    batch = BatchFactory(course__department__branch=branch, academic_year=year,
                         course__name="Class 5", name="A")
    user = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                       custom_login_id="STU-001", first_name="Rahul", last_name="Sharma",
                       must_change_password=False)
    user.set_password("Password123!")
    user.save()
    profile = StudentProfile.objects.create(user=user, current_batch=batch,
                                            guardian_phone="+919876543220")
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)
    return dict(user=user, batch=batch)


def test_get_profile_form(env):
    body = _data(_client(env["user"]).get(reverse("accounts:student-profile-form")))
    assert body["name"] == "Rahul Sharma"
    assert body["classLabel"] == "Class 5 - A"
    assert body["rollNumber"] == "STU-001"
    assert body["phone"] == "+919876543220"   # guardian contact
    assert body["editableFields"] == ["name", "ownPhone"]


def test_update_name_and_own_phone(env):
    url = reverse("accounts:student-profile-form")
    resp = _client(env["user"]).patch(
        url, {"name": "Rahul K Sharma", "ownPhone": "+919999999999"}, format="json")
    assert resp.status_code == 200, resp.content
    p = _data(resp)["profile"]
    assert p["name"] == "Rahul K Sharma"
    assert p["ownPhone"] == "+919999999999"
    env["user"].refresh_from_db()
    assert env["user"].phone == "+919999999999"


def test_change_password(env):
    url = reverse("accounts:student-profile-form")
    c = _client(env["user"])
    # Wrong current password rejected.
    bad = c.post(url, {"currentPassword": "wrong", "newPassword": "NewPass123!"}, format="json")
    assert bad.status_code == 400
    # Correct current password succeeds.
    ok = c.post(url, {"currentPassword": "Password123!", "newPassword": "NewPass123!"},
                format="json")
    assert ok.status_code == 200
    env["user"].refresh_from_db()
    assert env["user"].check_password("NewPass123!")
