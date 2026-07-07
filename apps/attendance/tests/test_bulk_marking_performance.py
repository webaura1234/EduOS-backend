"""Query-count regression test for bulk attendance marking.

Marking a session used to run ~5 queries per student (per-item student resolve,
leave check, upsert); a 500-student class meant 2000+ queries. mark_session now
batches all of that to a fixed number of queries regardless of class size.
"""

import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
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
from apps.attendance.models import AttendanceRecord
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
def big_class_env():
    tenant = TenantFactory(institution_type="school")
    TenantSettings.objects.create(tenant=tenant, attendance_mode=AttendanceMode.SESSION)
    branch = BranchFactory(tenant=tenant)
    year = AcademicYear.objects.create(
        branch=branch, name="2024-25", is_current=True,
        start_date=datetime.date(2024, 6, 1), end_date=datetime.date(2025, 4, 30),
    )
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type="term", sequence=1, name="Term 1",
        start_date=datetime.date(2024, 6, 1), end_date=datetime.date(2024, 10, 31),
    )
    dept = Department.objects.create(branch=branch, name="Science", department_type="stream")
    course = Course.objects.create(department=dept, name="Grade 9")
    batch = Batch.objects.create(course=course, academic_year=year, name="A")
    subject = Subject.objects.create(course=course, name="Maths", code="MTH9")
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    slot = PeriodSlot.objects.create(
        branch=branch, name="Period 1", sequence=1,
        start_time=datetime.time(9, 0), end_time=datetime.time(9, 45),
    )
    admin = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch,
        phone="+919820000001", custom_login_id=None, must_change_password=False,
    )
    faculty = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-BIG-1", must_change_password=False,
    )

    def make_students(n, offset):
        profiles = []
        for i in range(n):
            s = UserFactory(
                role=Role.STUDENT, tenant=tenant, branch=branch,
                custom_login_id=f"STU-BIG-{offset + i}", must_change_password=False,
            )
            p = StudentProfile.objects.create(user=s, current_batch=batch, academic_status=AcademicStatus.ACTIVE)
            StudentEnrollment.objects.create(branch=branch, student_profile=p, batch=batch, academic_year=year)
            profiles.append(p)
        return profiles

    return dict(
        branch=branch, batch=batch, bs=bs, slot=slot, admin=admin, faculty=faculty,
        make_students=make_students,
    )


def _open_session(env, date):
    c = _client(env["faculty"])
    resp = c.post(reverse("attendance:session-open"), {
        "batchSubjectId": str(env["bs"].id), "date": date.isoformat(),
        "periodSlotId": str(env["slot"].id),
    }, format="json")
    assert resp.status_code == 201, resp.content
    return _data(resp)["session"]["id"], c


def test_mark_session_query_count_does_not_scale_with_class_size(big_class_env):
    env = big_class_env
    small = env["make_students"](5, 0)
    date_small = datetime.date.today() - datetime.timedelta(days=2)
    sid_small, c_small = _open_session(env, date_small)
    payload_small = {"marks": [{"studentId": str(p.id), "status": "present"} for p in small]}
    with CaptureQueriesContext(connection) as ctx_small:
        resp = c_small.post(
            reverse("attendance:session-mark", kwargs={"session_id": sid_small}),
            payload_small, format="json",
        )
    assert resp.status_code == 200, resp.content
    queries_small = len(ctx_small.captured_queries)

    big = env["make_students"](120, 1000)
    date_big = datetime.date.today() - datetime.timedelta(days=1)
    sid_big, c_big = _open_session(env, date_big)
    payload_big = {"marks": [{"studentId": str(p.id), "status": "present"} for p in big]}
    with CaptureQueriesContext(connection) as ctx_big:
        resp2 = c_big.post(
            reverse("attendance:session-mark", kwargs={"session_id": sid_big}),
            payload_big, format="json",
        )
    assert resp2.status_code == 200, resp2.content
    queries_big = len(ctx_big.captured_queries)

    assert AttendanceRecord.objects.filter(session_id=sid_big).count() == 120
    # 24x the students (5 -> 120) must not multiply the query count — allow a
    # small constant slack for per-request overhead (auth, session lookups) but
    # reject anything that scales with N.
    assert queries_big <= queries_small + 3, (
        f"mark_session query count scales with class size: {queries_small} -> {queries_big}"
    )


def test_mark_session_is_idempotent_and_deduplicates_repeated_student_in_one_payload(big_class_env):
    env = big_class_env
    students = env["make_students"](3, 2000)
    sid, c = _open_session(env, datetime.date.today())
    # Same studentId twice in one payload — last one must win, and it must not
    # crash the bulk upsert (two rows sharing one idempotency_key in one INSERT).
    payload = {"marks": [
        {"studentId": str(students[0].id), "status": "present"},
        {"studentId": str(students[0].id), "status": "absent"},
        {"studentId": str(students[1].id), "status": "present"},
    ]}
    resp = c.post(reverse("attendance:session-mark", kwargs={"session_id": sid}), payload, format="json")
    assert resp.status_code == 200, resp.content
    assert AttendanceRecord.objects.filter(session_id=sid).count() == 2
    enrollment = StudentEnrollment.objects.get(student_profile_id=students[0].id, is_active=True)
    rec = AttendanceRecord.objects.get(session_id=sid, student_id=enrollment.id)
    assert rec.status == "absent"  # last mark for the repeated studentId wins
