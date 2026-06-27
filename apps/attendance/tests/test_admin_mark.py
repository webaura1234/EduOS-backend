"""Admin mark attendance context — branch admin bulk marking."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import (
    AcademicPeriod,
    AcademicYear,
    Batch,
    BatchSubject,
    Course,
    Department,
    Holiday,
    PeriodSlot,
    Subject,
)
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.models import StudentEnrollment
from apps.organizations.enums import AttendanceMode
from apps.organizations.models import TenantSettings
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
    TenantSettings.objects.create(
        tenant=tenant,
        attendance_threshold_percent=75,
        exam_day_counts_toward_attendance=True,
        attendance_mode=AttendanceMode.DAY,
    )
    branch = BranchFactory(tenant=tenant)
    year = AcademicYear.objects.create(
        branch=branch,
        name="2024-25",
        is_current=True,
        start_date=datetime.date(2024, 6, 1),
        end_date=datetime.date(2025, 4, 30),
    )
    AcademicPeriod.objects.create(
        academic_year=year,
        period_type="term",
        sequence=1,
        name="Term 1",
        start_date=datetime.date(2024, 6, 1),
        end_date=datetime.date(2024, 10, 31),
    )
    dept = Department.objects.create(branch=branch, name="Science", department_type="stream")
    course = Course.objects.create(department=dept, name="Grade 9")
    batch = Batch.objects.create(course=course, academic_year=year, name="A")
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919810000099",
        custom_login_id=None,
        must_change_password=False,
    )
    s1 = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="STU-1",
        must_change_password=False,
    )
    p1 = StudentProfile.objects.create(user=s1, current_batch=batch, academic_status=AcademicStatus.ACTIVE)
    StudentEnrollment.objects.create(branch=branch, student_profile=p1, batch=batch, academic_year=year)
    return dict(tenant=tenant, branch=branch, batch=batch, admin=admin, p1=p1)


@pytest.fixture
def session_env():
    tenant = TenantFactory(institution_type="school")
    TenantSettings.objects.create(
        tenant=tenant,
        attendance_mode=AttendanceMode.SESSION,
    )
    branch = BranchFactory(tenant=tenant)
    year = AcademicYear.objects.create(
        branch=branch,
        name="2024-25",
        is_current=True,
        start_date=datetime.date(2024, 6, 1),
        end_date=datetime.date(2025, 4, 30),
    )
    period = AcademicPeriod.objects.create(
        academic_year=year,
        period_type="term",
        sequence=1,
        name="Term 1",
        start_date=datetime.date(2024, 6, 1),
        end_date=datetime.date(2024, 10, 31),
    )
    dept = Department.objects.create(branch=branch, name="Science", department_type="stream")
    course = Course.objects.create(department=dept, name="Grade 9")
    batch = Batch.objects.create(course=course, academic_year=year, name="A")
    subject = Subject.objects.create(course=course, name="Maths", code="MTH9")
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    slot = PeriodSlot.objects.create(
        branch=branch,
        name="Period 1",
        sequence=1,
        start_time=datetime.time(9, 0),
        end_time=datetime.time(9, 45),
    )
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919810000098",
        custom_login_id=None,
        must_change_password=False,
    )
    return dict(branch=branch, batch=batch, bs=bs, slot=slot, admin=admin)


def test_mark_metadata_without_batch(env):
    resp = _client(env["admin"]).get(reverse("attendance:admin-mark"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert body["mode"] == "day"
    assert body["holiday"]["blocked"] is False
    assert isinstance(body["classSections"], list)
    assert body["records"] == []


def test_mark_day_mode_returns_roster(env):
    today = datetime.date.today().isoformat()
    url = reverse("attendance:admin-mark")
    resp = _client(env["admin"]).get(url, {"date": today, "batchId": str(env["batch"].id)})
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert body["sessionId"]
    assert len(body["records"]) == 1
    assert body["records"][0]["studentId"] == str(env["p1"].id)


def test_mark_holiday_blocked(env):
    today = datetime.date.today()
    Holiday.objects.create(
        branch=env["branch"],
        date=today,
        name="Festival",
        holiday_type="public",
        applies_to={"all": True},
    )
    resp = _client(env["admin"]).get(
        reverse("attendance:admin-mark"),
        {"date": today.isoformat(), "batchId": str(env["batch"].id)},
    )
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert body["holiday"]["blocked"] is True
    assert body["records"] == []


def test_mark_session_mode_requires_subject_and_period(session_env):
    today = datetime.date.today().isoformat()
    batch_id = str(session_env["batch"].id)
    resp = _client(session_env["admin"]).get(
        reverse("attendance:admin-mark"),
        {"date": today, "batchId": batch_id},
    )
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert body["mode"] == "session"
    assert body["records"] == []
    assert len(body["subjects"]) == 1


def test_mark_future_date_rejected(env):
    future = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    resp = _client(env["admin"]).get(
        reverse("attendance:admin-mark"),
        {"date": future, "batchId": str(env["batch"].id)},
    )
    assert resp.status_code == 400
