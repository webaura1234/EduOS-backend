"""Substitution available-faculty endpoint and availability rules."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import PeriodSlot, Timetable, TimetableEntry
from apps.academics.models.curriculum import BatchSubject, Subject
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.hr.enums import LeaveStatus
from apps.hr.models import Employee, LeaveApplication
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
    admin = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch,
        phone="+919810000099", custom_login_id=None, must_change_password=False,
    )
    teacher = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-T1", must_change_password=False,
        first_name="Priya", last_name="Patel",
    )
    substitute = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-T2", must_change_password=False,
        first_name="Ravi", last_name="Kumar",
    )
    busy = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-T3", must_change_password=False,
        first_name="Busy", last_name="Teacher",
    )
    return dict(
        tenant=tenant, branch=branch, admin=admin,
        teacher=teacher, substitute=substitute, busy=busy,
    )


def _timetable_setup(env, *, faculty, day_of_week=0, sequence=1):
    year = AcademicYearFactory(branch=env["branch"])
    batch = BatchFactory(course__department__branch=env["branch"], academic_year=year)
    subject = Subject.objects.create(course=batch.course, name="Maths", code="MA")
    from apps.academics.models.calendar import AcademicPeriod, PeriodType
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type=PeriodType.TERM, sequence=1, name="Term 1",
        start_date=datetime.date(2025, 6, 1), end_date=datetime.date(2025, 10, 1),
    )
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    slot = PeriodSlot.objects.create(
        branch=env["branch"], name="P1", sequence=sequence,
        start_time=datetime.time(9, 0), end_time=datetime.time(10, 0),
    )
    tt = Timetable.objects.create(batch=batch, academic_period=period)
    entry = TimetableEntry.objects.create(
        timetable=tt, batch_subject=bs, period_slot=slot, day_of_week=day_of_week,
        faculty=faculty, status="active",
    )
    return dict(year=year, batch=batch, subject=subject, period=period, bs=bs, slot=slot, tt=tt, entry=entry)


def _available_url():
    return reverse("academics:substitution-available-faculty")


def test_original_teacher_excluded(env):
    setup = _timetable_setup(env, faculty=env["teacher"], day_of_week=0)
    # 2026-06-22 is a Monday (weekday 0)
    resp = _client(env["admin"]).get(_available_url(), {
        "timetableSlotId": str(setup["entry"].id),
        "date": "2026-06-22",
    })
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert body["originalFacultyUserId"] == str(env["teacher"].id)
    assert body["originalFacultyName"] == "Priya Patel"
    ids = {f["userId"] for f in body["availableFaculty"]}
    assert str(env["teacher"].id) not in ids
    assert str(env["substitute"].id) in ids


def test_faculty_with_period_clash_excluded(env):
    setup = _timetable_setup(env, faculty=env["teacher"], day_of_week=0, sequence=1)
    year = AcademicYearFactory(branch=env["branch"])
    batch2 = BatchFactory(course__department__branch=env["branch"], academic_year=year)
    subject2 = Subject.objects.create(course=batch2.course, name="Science", code="SC")
    from apps.academics.models.calendar import AcademicPeriod, PeriodType
    period2 = AcademicPeriod.objects.create(
        academic_year=year, period_type=PeriodType.TERM, sequence=1, name="Term 1",
        start_date=datetime.date(2025, 6, 1), end_date=datetime.date(2025, 10, 1),
    )
    bs2 = BatchSubject.objects.create(batch=batch2, subject=subject2, academic_period=period2)
    tt2 = Timetable.objects.create(batch=batch2, academic_period=period2)
    TimetableEntry.objects.create(
        timetable=tt2, batch_subject=bs2, period_slot=setup["slot"], day_of_week=0,
        faculty=env["busy"], status="active",
    )
    resp = _client(env["admin"]).get(_available_url(), {
        "timetableSlotId": str(setup["entry"].id),
        "date": "2026-06-22",
    })
    body = _data(resp)
    ids = {f["userId"] for f in body["availableFaculty"]}
    assert str(env["busy"].id) not in ids
    assert str(env["substitute"].id) in ids


def test_faculty_on_approved_leave_excluded(env):
    setup = _timetable_setup(env, faculty=env["teacher"], day_of_week=0)
    emp = Employee.objects.create(
        user=env["substitute"], branch=env["branch"], employee_code="FAC-T2",
        employment_type="full_time", joined_at=datetime.date(2024, 1, 1),
    )
    LeaveApplication.objects.create(
        employee=emp, leave_type="casual",
        from_date=datetime.date(2026, 6, 22), to_date=datetime.date(2026, 6, 22),
        days=1, reason="Sick", status=LeaveStatus.APPROVED,
    )
    resp = _client(env["admin"]).get(_available_url(), {
        "timetableSlotId": str(setup["entry"].id),
        "date": "2026-06-22",
    })
    body = _data(resp)
    ids = {f["userId"] for f in body["availableFaculty"]}
    assert str(env["substitute"].id) not in ids


def test_create_substitution_rejects_unavailable(env):
    setup = _timetable_setup(env, faculty=env["teacher"], day_of_week=0)
    resp = _client(env["admin"]).post(
        reverse("academics:admin-actions"),
        {"action": "create_substitution", "payload": {
            "timetableSlotId": str(setup["entry"].id),
            "substituteFacultyUserId": str(env["teacher"].id),
            "date": "2026-06-22",
            "reason": "Self",
        }},
        format="json",
    )
    assert resp.status_code == 400, resp.content
