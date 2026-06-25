"""Report period helpers and ranking vs detention split."""

import datetime

import pytest

from apps.academics.models import (
    AcademicPeriod,
    AcademicYear,
    Batch,
    BatchSubject,
    Course,
    Department,
    PeriodSlot,
    Subject,
)
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.admissions.models import StudentEnrollment
from apps.attendance.enums import SessionStatus
from apps.attendance.helpers import iso_week_bounds, parse_month_param, parse_week_param
from apps.attendance.interactors import report as report_i
from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.organizations.models import TenantSettings
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    TenantSettings.objects.create(
        tenant=tenant, attendance_threshold_percent=75, exam_day_counts_toward_attendance=True
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
    s1 = UserFactory(
        role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-1", must_change_password=False
    )
    s2 = UserFactory(
        role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-2", must_change_password=False
    )
    p1 = StudentProfile.objects.create(user=s1, current_batch=batch, academic_status=AcademicStatus.ACTIVE)
    p2 = StudentProfile.objects.create(user=s2, current_batch=batch, academic_status=AcademicStatus.ACTIVE)
    e1 = StudentEnrollment.objects.create(branch=branch, student_profile=p1, batch=batch, academic_year=year)
    e2 = StudentEnrollment.objects.create(branch=branch, student_profile=p2, batch=batch, academic_year=year)
    return dict(branch=branch, batch=batch, bs=bs, slot=slot, p1=p1, p2=p2, e1=e1, e2=e2)


def _seed_july_sessions(env):
    for i in range(4):
        sess = AttendanceSession.objects.create(
            branch=env["branch"],
            batch=env["batch"],
            batch_subject=env["bs"],
            period_slot=env["slot"],
            date=datetime.date(2024, 7, i + 1),
            status=SessionStatus.COMPLETED,
        )
        AttendanceRecord.objects.create(
            session=sess,
            student=env["e1"],
            status="present" if i == 0 else "absent",
            marked_at=datetime.datetime.now(),
            idempotency_key=f"{sess.id}:{env['p1'].id}",
        )
        AttendanceRecord.objects.create(
            session=sess,
            student=env["e2"],
            status="present",
            marked_at=datetime.datetime.now(),
            idempotency_key=f"{sess.id}:{env['p2'].id}",
        )


def test_parse_week_param_iso_week_string():
    start, end = parse_week_param("2024-W01")
    assert start == datetime.date(2024, 1, 1)
    assert end == datetime.date(2024, 1, 7)


def test_parse_month_param():
    start, end = parse_month_param("2024-07")
    assert start == datetime.date(2024, 7, 1)
    assert end == datetime.date(2024, 7, 31)


def test_iso_week_bounds():
    start, end = iso_week_bounds(2024, 1)
    assert (end - start).days == 6


def test_ranking_includes_all_students_detention_only_below(env):
    _seed_july_sessions(env)
    date_from = datetime.date(2024, 7, 1)
    date_to = datetime.date(2024, 7, 31)
    ranking = report_i.ranking_report(env["branch"], date_from=date_from, date_to=date_to)
    detention = report_i.detention_report(env["branch"], date_from=date_from, date_to=date_to)
    ranking_ids = {r["studentId"] for r in ranking["rows"]}
    detention_ids = {r["studentId"] for r in detention["rows"]}
    assert len(ranking_ids) == 2
    assert len(detention_ids) == 1
    assert detention_ids.issubset(ranking_ids)
