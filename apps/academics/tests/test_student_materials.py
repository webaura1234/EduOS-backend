"""Student-facing study materials endpoint."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import PeriodSlot, Timetable, TimetableEntry
from apps.academics.models.calendar import AcademicPeriod, PeriodType
from apps.academics.models.curriculum import BatchSubject, Subject
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
    subject = Subject.objects.create(course=batch.course, name="Mathematics", code="MA")
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type=PeriodType.TERM, sequence=1, name="Term 1",
        start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 12, 1),
    )
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    slot = PeriodSlot.objects.create(branch=branch, name="P1", sequence=1,
                                     start_time=datetime.time(9, 0), end_time=datetime.time(10, 0))
    tt = Timetable.objects.create(batch=batch, academic_period=period)
    entry = TimetableEntry.objects.create(timetable=tt, batch_subject=bs, period_slot=slot,
                                          day_of_week=1, status="active")
    StudyMaterial.objects.create(branch=branch, timetable_entry=entry,
                                 session_date=datetime.date(2026, 6, 22),
                                 file_name="Unit-1-notes.pdf", s3_key="materials/u1.pdf")

    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                          custom_login_id="STU-1", must_change_password=False)
    profile = StudentProfile.objects.create(user=student)
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)

    resp = _client(student).get(reverse("academics:student-materials"))
    assert resp.status_code == 200, resp.content
    materials = _data(resp)["materials"]
    assert len(materials) == 1
    assert materials[0]["fileName"] == "Unit-1-notes.pdf"
    assert materials[0]["subjectName"] == "Mathematics"
    assert materials[0]["unitTitles"] == []


def test_student_without_enrollment_gets_empty():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                          custom_login_id="STU-2", must_change_password=False)
    StudentProfile.objects.create(user=student)
    resp = _client(student).get(reverse("academics:student-materials"))
    assert resp.status_code == 200, resp.content
    assert _data(resp)["materials"] == []
