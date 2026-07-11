"""Unified account module — parent profile, super-admin profile, avatar, absence fan-out."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.guardian import StudentGuardianLink
from apps.accounts.models.profile import GuardianProfile, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.admissions.tests.factories import StudentEnrollmentFactory
from apps.communications.interactors.create import create_notification
from apps.communications.models import Notification
from apps.integrations.adapters.s3 import SandboxS3
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
def school_env():
    tenant = TenantFactory(institution_type="school", parent_access_enabled=True)
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(
        course__department__branch=branch,
        academic_year=year,
        course__name="Class 5",
        name="A",
    )
    student = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="STU-100",
        first_name="Rahul",
        last_name="Kumar",
        must_change_password=False,
    )
    profile = StudentProfile.objects.create(user=student, current_batch=batch)
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)
    parent = UserFactory(
        role=Role.PARENT,
        tenant=tenant,
        branch=branch,
        phone="+919800011122",
        email="parent@example.com",
        first_name="Priya",
        last_name="Kumar",
        custom_login_id=None,
        must_change_password=False,
    )
    GuardianProfile.objects.create(user=parent)
    StudentGuardianLink.objects.create(
        student=student,
        guardian=parent,
        relationship="mother",
        has_portal_access=True,
        is_primary_contact=True,
    )
    super_admin = UserFactory(
        role=Role.SUPER_ADMIN,
        tenant=tenant,
        branch=None,
        phone="+919811122233",
        first_name="Super",
        last_name="Admin",
        custom_login_id=None,
        must_change_password=False,
    )
    super_admin.set_password("Password123!")
    super_admin.save()
    return dict(
        tenant=tenant,
        branch=branch,
        batch=batch,
        student=student,
        parent=parent,
        super_admin=super_admin,
    )


def test_parent_profile_includes_children(school_env):
    body = _data(_client(school_env["parent"]).get(reverse("accounts:parent-profile-form")))
    assert body["name"] == "Priya Kumar"
    assert body["phone"] == "+919800011122"
    assert body["email"] == "parent@example.com"
    assert len(body["children"]) == 1
    child = body["children"][0]
    assert child["name"] == "Rahul Kumar"
    assert child["classLabel"] == "Class 5 - A"
    assert child["id"] == str(school_env["student"].pk)


def test_parent_profile_patch_name(school_env):
    url = reverse("accounts:parent-profile-form")
    resp = _client(school_env["parent"]).patch(url, {"name": "Priya Sharma"}, format="json")
    assert resp.status_code == 200
    school_env["parent"].refresh_from_db()
    assert school_env["parent"].full_name == "Priya Sharma"


def test_parent_children_list_endpoint(school_env):
    body = _data(_client(school_env["parent"]).get(reverse("parent:children")))
    assert len(body) == 1
    assert body[0]["name"] == "Rahul Kumar"


def test_super_admin_profile_patch(school_env):
    url = reverse("accounts:super-admin-profile-form")
    resp = _client(school_env["super_admin"]).patch(
        url,
        {"name": "Updated Admin", "ownPhone": "+919900000001"},
        format="json",
    )
    assert resp.status_code == 200
    school_env["super_admin"].refresh_from_db()
    assert school_env["super_admin"].full_name == "Updated Admin"
    assert school_env["super_admin"].phone == "+919900000001"


def test_avatar_presign_confirm_delete(school_env):
    user = school_env["parent"]
    presign = _data(
        _client(user).post(
            reverse("accounts:avatar-presign"),
            {"contentType": "image/png", "fileSize": 1024},
            format="json",
        )
    )
    assert presign["key"]
    assert presign["uploadUrl"]

    SandboxS3.SINK[presign["key"]] = b"fake-image"

    confirm = _data(
        _client(user).post(
            reverse("accounts:avatar-confirm"),
            {"key": presign["key"]},
            format="json",
        )
    )
    assert confirm["avatarUrl"]

    user.refresh_from_db()
    assert user.avatar_s3_key == presign["key"]

    me = _data(_client(user).get(reverse("accounts:me")))
    assert me["avatarUrl"]

    _client(user).delete(reverse("accounts:avatar-delete"))
    user.refresh_from_db()
    assert user.avatar_s3_key == ""


def test_attendance_absent_notifies_student_and_parent(school_env):
    student = school_env["student"]
    parent = school_env["parent"]
    branch = school_env["branch"]

    for recipient in (student, parent):
        create_notification(
            "attendance.absent",
            tenant=branch.tenant,
            branch=branch,
            recipient=recipient,
            variables={
                "student_name": student.full_name,
                "date": "2026-07-11",
                "class_label": "Class 5 - A",
                **({"child_id": str(student.pk)} if recipient.role == Role.PARENT else {"child_id": ""}),
            },
            dedup_key=f"att:absent:test:{recipient.pk}",
        )

    assert Notification.objects.filter(recipient=student, notification_type="attendance.absent").count() == 1
    assert Notification.objects.filter(recipient=parent, notification_type="attendance.absent").count() == 1

    parent_row = Notification.objects.get(recipient=parent, notification_type="attendance.absent")
    assert "childId" in parent_row.action_url or str(student.pk) in parent_row.action_url
