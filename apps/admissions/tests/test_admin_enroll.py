"""Admin enroll-from-application flow."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.queries import application as app_q
from apps.admissions.queries import enquiry as enq_q
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
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    return dict(tenant=tenant, branch=branch, admin=admin, year=year, batch=batch)


def _make_application(env, name="Ravi Kumar", phone="+919800000001"):
    enq = enq_q.create_enquiry(
        branch=env["branch"], source="walk_in", applicant_name=name, phone=phone,
        course=env["batch"].course,
    )
    return app_q.create_application(
        branch=env["branch"], enquiry=enq, course=env["batch"].course, status="accepted",
    )


def test_enroll_creates_student(env):
    application = _make_application(env)
    resp = _client(env["admin"]).post(
        reverse("admissions:enroll-from-application", args=[application.id]),
        {}, format="json",
    )
    assert resp.status_code == 201, resp.content
    assert "studentUserId" in _data(resp)


def test_enroll_no_batch_errors(env):
    # Application whose course has no batch in the current year.
    from apps.academics.queries.structure import create_course, create_department
    dept = create_department(env["branch"].pk, name="Other", department_type="department")
    course = create_course(department=dept, name="No-Batch Course")
    enq = enq_q.create_enquiry(branch=env["branch"], source="online",
                               applicant_name="Asha", phone="+919800000002", course=course)
    application = app_q.create_application(branch=env["branch"], enquiry=enq,
                                           course=course, status="accepted")
    resp = _client(env["admin"]).post(
        reverse("admissions:enroll-from-application", args=[application.id]),
        {}, format="json",
    )
    assert resp.status_code == 400


def test_enroll_requires_admin(env):
    application = _make_application(env, name="X", phone="+919800000009")
    student = UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
                          custom_login_id="STU-Z", must_change_password=False)
    resp = _client(student).post(
        reverse("admissions:enroll-from-application", args=[application.id]),
        {}, format="json",
    )
    assert resp.status_code == 403
