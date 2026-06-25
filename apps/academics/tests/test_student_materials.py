"""Student-facing study materials endpoint."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models.admin_extras import StudyMaterial
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


def test_student_sees_materials_for_their_batch():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)

    StudyMaterial.objects.create(
        branch=branch, batch=batch, file_name="Unit-1-notes.pdf", s3_key="materials/u1.pdf",
    )

    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                          custom_login_id="STU-1", must_change_password=False)
    profile = StudentProfile.objects.create(user=student)
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)

    resp = _client(student).get(reverse("academics:student-materials"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert len(body["general"]) == 1
    assert body["general"][0]["fileName"] == "Unit-1-notes.pdf"
    assert batch.course.name in body["general"][0]["classLabel"]
    assert body["general"][0]["unitTitles"] == []
    assert body["folders"] == []


def test_student_without_enrollment_gets_empty():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                          custom_login_id="STU-2", must_change_password=False)
    StudentProfile.objects.create(user=student)
    resp = _client(student).get(reverse("academics:student-materials"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert body["folders"] == []
    assert body["general"] == []
