"""Super-admin operations overview + tenant-wide user management."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
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
def multi_branch_env():
    tenant = TenantFactory(institution_type="school")
    branch_a = BranchFactory(tenant=tenant, name="Campus A", code="A")
    branch_b = BranchFactory(tenant=tenant, name="Campus B", code="B")
    super_admin = UserFactory(
        role=Role.SUPER_ADMIN,
        tenant=tenant,
        branch=None,
        phone="+919830000099",
        must_change_password=False,
    )
    admin_a = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch_a,
        phone="+919830000001",
        must_change_password=False,
    )
    faculty_a = UserFactory(
        role=Role.FACULTY,
        tenant=tenant,
        branch=branch_a,
        custom_login_id="FAC-A-01",
        must_change_password=False,
    )
    faculty_b = UserFactory(
        role=Role.FACULTY,
        tenant=tenant,
        branch=branch_b,
        custom_login_id="FAC-B-01",
        must_change_password=False,
    )
    year = AcademicYearFactory(branch=branch_a, is_current=True)
    batch = BatchFactory(course__department__branch=branch_a, academic_year=year)
    student_user = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch_a,
        custom_login_id="STU-A-01",
        must_change_password=False,
    )
    profile = StudentProfile.objects.create(user=student_user, current_batch=batch)
    StudentEnrollmentFactory(student_profile=profile, branch=branch_a, batch=batch)
    return dict(
        tenant=tenant,
        branch_a=branch_a,
        branch_b=branch_b,
        super_admin=super_admin,
        admin_a=admin_a,
        faculty_a=faculty_a,
        faculty_b=faculty_b,
    )


def test_operations_overview_counts(multi_branch_env):
    env = multi_branch_env
    resp = _client(env["super_admin"]).get(reverse("accounts:super-admin-operations-overview"))
    assert resp.status_code == 200
    body = _data(resp)
    assert body["totals"]["admins"] >= 1
    assert body["totals"]["faculty"] >= 2
    assert body["totals"]["students"] >= 1
    rows = {r["branchId"]: r for r in body["branches"]}
    assert str(env["branch_a"].pk) in rows
    assert rows[str(env["branch_a"].pk)]["faculty"] >= 1


def test_super_admin_lists_all_users(multi_branch_env):
    env = multi_branch_env
    resp = _client(env["super_admin"]).get(reverse("accounts:users-management"))
    assert resp.status_code == 200
    body = _data(resp)
    assert body["branchScope"] == "all"
    roles = {u["role"] for u in body["users"]}
    assert "faculty" in roles
    assert len(body["users"]) >= 3


def test_super_admin_filters_users_by_branch(multi_branch_env):
    env = multi_branch_env
    url = reverse("accounts:users-management") + f"?branch={env['branch_b'].pk}"
    resp = _client(env["super_admin"]).get(url)
    assert resp.status_code == 200
    body = _data(resp)
    assert body["branchScope"] == str(env["branch_b"].pk)
    assert all(u["branch"] == str(env["branch_b"].pk) for u in body["users"])


def test_branch_admin_still_scoped(multi_branch_env):
    env = multi_branch_env
    resp = _client(env["admin_a"]).get(reverse("accounts:users-management"))
    assert resp.status_code == 200
    body = _data(resp)
    assert body["branchId"] == str(env["branch_a"].pk)
    for u in body["users"]:
        assert u["branch"] == str(env["branch_a"].pk)
