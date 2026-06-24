"""Faculty timetable — weekly schedule, calendar, holidays, leave overlays."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import PeriodSlot, Timetable, TimetableEntry
from apps.academics.models.calendar import AcademicPeriod, PeriodType
from apps.academics.models.curriculum import BatchSubject, Subject
from apps.academics.queries import holiday as hol_q
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.hr.models import Employee, LeaveApplication
from apps.hr.enums import LeaveStatus
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def _setup_faculty_slot(*, branch, year, faculty, day, published=True, subject_name="Maths", batch=None):
    if batch is None:
        batch = BatchFactory(course__department__branch=branch, academic_year=year)
    subject = Subject.objects.create(course=batch.course, name=subject_name, code=f"SUB-{subject_name[:3]}")
    period, _ = AcademicPeriod.objects.get_or_create(
        academic_year=year,
        sequence=1,
        defaults=dict(
            period_type=PeriodType.TERM,
            name="T1",
            start_date=datetime.date(2026, 1, 1),
            end_date=datetime.date(2026, 12, 31),
        ),
    )
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    slot, _ = PeriodSlot.objects.get_or_create(
        branch=branch, sequence=1,
        defaults=dict(name="P1", start_time=datetime.time(9, 0), end_time=datetime.time(9, 45)),
    )
    tt, _ = Timetable.objects.get_or_create(
        batch=batch, academic_period=period,
        defaults=dict(is_published=published),
    )
    if not tt.is_published and published:
        tt.is_published = True
        tt.save(update_fields=["is_published"])
    entry = TimetableEntry.objects.create(
        timetable=tt, batch_subject=bs, period_slot=slot,
        day_of_week=day, faculty=faculty, status="active",
    )
    return batch, entry, bs, slot


def test_faculty_weekly_timetable():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    faculty = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-1", must_change_password=False,
    )
    batch, _, _, _ = _setup_faculty_slot(branch=branch, year=year, faculty=faculty, day=1)
    _setup_faculty_slot(branch=branch, year=year, faculty=faculty, day=2, subject_name="Science", batch=batch)

    body = _data(_client(faculty).get(reverse("academics:faculty-timetable")))
    assert "weekly" in body
    assert len(body["weekly"]["days"]) == 2
    subjects = [p["subjectName"] for d in body["weekly"]["days"] for p in d["periods"]]
    assert "Maths" in subjects
    assert "Science" in subjects
    assert "slotLabel" not in str(body)


def test_unpublished_timetable_excluded():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    faculty = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-1", must_change_password=False,
    )
    _setup_faculty_slot(branch=branch, year=year, faculty=faculty, day=1, published=False)

    body = _data(_client(faculty).get(reverse("academics:faculty-timetable")))
    assert body["weekly"]["days"] == []


def test_holiday_on_calendar():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    faculty = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-1", must_change_password=False,
    )
    today = datetime.date.today()
    hol_q.create_holiday(
        branch.pk, date=today, name="Republic Day",
        holiday_type="public", user=faculty,
    )

    body = _data(_client(faculty).get(
        reverse("academics:faculty-timetable"),
        {"year": today.year, "month": today.month},
    ))
    day = next(d for d in body["calendar"]["days"] if d["date"] == today.isoformat())
    assert day["dayKind"] == "holiday"
    assert day["holidayName"] == "Republic Day"


def test_leave_overlay():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    faculty = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-1", must_change_password=False,
    )
    emp = Employee.objects.create(
        user=faculty, branch=branch, employee_code="E001",
        employment_type="full_time", joined_at=datetime.date(2020, 1, 1),
    )
    today = datetime.date.today()
    LeaveApplication.objects.create(
        employee=emp, leave_type="casual", from_date=today, to_date=today,
        days=1, reason="Family function", status=LeaveStatus.APPROVED,
    )

    body = _data(_client(faculty).get(
        reverse("academics:faculty-timetable"),
        {"year": today.year, "month": today.month, "date": today.isoformat()},
    ))
    day = next(d for d in body["calendar"]["days"] if d["date"] == today.isoformat())
    assert day["dayKind"] == "leave"
    assert body["dayDetail"]["dayKind"] == "leave"
    assert body["dayDetail"]["leaveReason"] == "Family function"


def test_day_detail_staff_attendance():
    from apps.hr.queries import staff_attendance as sa_q

    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    faculty = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-1", must_change_password=False,
    )
    today = datetime.date.today()

    body = _data(_client(faculty).get(
        reverse("academics:faculty-timetable"),
        {"year": today.year, "month": today.month, "date": today.isoformat()},
    ))
    assert body["dayDetail"]["staffStatus"] == "not_marked"
    assert body["dayDetail"]["canCheckIn"] is True
    assert "sessions" not in body["dayDetail"]

    sa_q.check_in(branch, faculty)
    body2 = _data(_client(faculty).get(
        reverse("academics:faculty-timetable"),
        {"year": today.year, "month": today.month, "date": today.isoformat()},
    ))
    assert body2["dayDetail"]["staffStatus"] == "present"
    assert body2["dayDetail"]["canCheckIn"] is False


def test_requires_faculty():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    student = UserFactory(
        role=Role.STUDENT, tenant=tenant, branch=branch,
        custom_login_id="STU-1", must_change_password=False,
    )
    resp = _client(student).get(reverse("academics:faculty-timetable"))
    assert resp.status_code == 403
