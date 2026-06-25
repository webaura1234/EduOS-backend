"""Live board snapshot — roster denominator and cache invalidation."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import (
    AcademicPeriod, AcademicYear, Batch, BatchSubject, Course, Department, PeriodSlot, Subject,
)
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.models import StudentEnrollment
from apps.attendance.interactors import live_board as live_i
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
    TenantSettings.objects.create(tenant=tenant, attendance_threshold_percent=75,
                                  exam_day_counts_toward_attendance=True)
    branch = BranchFactory(tenant=tenant)
    year = AcademicYear.objects.create(branch=branch, name="2024-25", is_current=True,
                                       start_date=datetime.date(2024, 6, 1), end_date=datetime.date(2025, 4, 30))
    period = AcademicPeriod.objects.create(academic_year=year, period_type="term", sequence=1,
                                           name="Term 1", start_date=datetime.date(2024, 6, 1),
                                           end_date=datetime.date(2024, 10, 31))
    dept = Department.objects.create(branch=branch, name="Science", department_type="stream")
    course = Course.objects.create(department=dept, name="Grade 9")
    batch = Batch.objects.create(course=course, academic_year=year, name="A")
    subject = Subject.objects.create(course=course, name="Maths", code="MTH9")
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    slot = PeriodSlot.objects.create(branch=branch, name="Period 1", sequence=1,
                                     start_time=datetime.time(9, 0), end_time=datetime.time(9, 45))
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919800000099",
                        custom_login_id=None, must_change_password=False)
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch, custom_login_id="FAC-LIVE",
                          must_change_password=False)
    students = []
    for i in range(1, 4):
        user = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                           custom_login_id=f"STU-L{i}", must_change_password=False)
        profile = StudentProfile.objects.create(user=user, current_batch=batch,
                                                academic_status=AcademicStatus.ACTIVE)
        StudentEnrollment.objects.create(branch=branch, student_profile=profile, batch=batch, academic_year=year)
        students.append(profile)
    return dict(branch=branch, batch=batch, bs=bs, slot=slot, admin=admin, faculty=faculty, students=students)


def _open_and_mark_one_present(env):
    c = _client(env["faculty"])
    today = datetime.date.today()
    open_resp = c.post(reverse("attendance:session-open"), {
        "batchSubjectId": str(env["bs"].id),
        "date": today.isoformat(),
        "periodSlotId": str(env["slot"].id),
    }, format="json")
    assert open_resp.status_code == 201, open_resp.content
    sid = _data(open_resp)["session"]["id"]
    mark_resp = c.post(reverse("attendance:session-mark", kwargs={"session_id": sid}), {
        "marks": [{"studentId": str(env["students"][0].id), "status": "present"}],
    }, format="json")
    assert mark_resp.status_code == 200, mark_resp.content


def test_live_snapshot_uses_roster_as_total(env):
    _open_and_mark_one_present(env)
    live_i.invalidate_live_cache(env["branch"].pk)

    resp = _client(env["admin"]).get(reverse("attendance:admin-live"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)

    assert body["present"] == 1
    assert body["total"] == 3
    assert body["percent"] == 33
    assert len(body["classes"]) == 1
    assert body["classes"][0]["present"] == 1
    assert body["classes"][0]["total"] == 3


def test_live_and_legacy_path_share_snapshot(env):
    _open_and_mark_one_present(env)
    live_i.invalidate_live_cache(env["branch"].pk)
    client = _client(env["admin"])
    admin_live = _data(client.get(reverse("attendance:admin-live")))
    board_live = _data(client.get(reverse("attendance:live")))
    assert admin_live == board_live
