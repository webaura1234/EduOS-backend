"""Faculty attendance read aggregate (today's classes + records + holiday + geofence)."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import PeriodSlot, Timetable, TimetableEntry
from apps.academics.models.calendar import AcademicPeriod, PeriodType
from apps.academics.models.curriculum import BatchSubject, Subject
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def test_faculty_sees_todays_classes():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    subject = Subject.objects.create(course=batch.course, name="Maths", code="MA")
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                          custom_login_id="FAC-1", must_change_password=False)
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type=PeriodType.TERM, sequence=1, name="T1",
        start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 12, 1),
    )
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    slot = PeriodSlot.objects.create(branch=branch, name="P1", sequence=1,
                                     start_time=datetime.time(9, 0), end_time=datetime.time(10, 0))
    tt = Timetable.objects.create(batch=batch, academic_period=period)
    TimetableEntry.objects.create(
        timetable=tt, batch_subject=bs, period_slot=slot,
        day_of_week=datetime.date.today().isoweekday(), faculty=faculty, status="active",
    )

    body = _data(_client(faculty).get(reverse("attendance:faculty-attendance")))
    assert set(body) == {"date", "sessions", "records", "holiday", "geoFence"}
    assert len(body["sessions"]) == 1
    assert body["sessions"][0]["subjectName"] == "Maths"
    assert body["geoFence"]["enabled"] is False


def test_get_creates_roster_records_nondestructively():
    from apps.accounts.models.profile import StudentProfile
    from apps.admissions.tests.factories import StudentEnrollmentFactory
    from apps.attendance.models import AttendanceRecord

    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    subject = Subject.objects.create(course=batch.course, name="Sci", code="SC")
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                          custom_login_id="FAC-1", must_change_password=False)
    su = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                     custom_login_id="STU-1", first_name="Ravi", must_change_password=False)
    profile = StudentProfile.objects.create(user=su, current_batch=batch)
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type=PeriodType.TERM, sequence=1, name="T1",
        start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 12, 1))
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    slot = PeriodSlot.objects.create(branch=branch, name="P1", sequence=1,
                                     start_time=datetime.time(9, 0), end_time=datetime.time(10, 0))
    tt = Timetable.objects.create(batch=batch, academic_period=period)
    TimetableEntry.objects.create(
        timetable=tt, batch_subject=bs, period_slot=slot,
        day_of_week=datetime.date.today().isoweekday(), faculty=faculty, status="active")

    c = _client(faculty)
    body = _data(c.get(reverse("attendance:faculty-attendance")))
    assert len(body["records"]) == 1
    rec_id = body["records"][0]["id"]
    assert body["records"][0]["status"] == "absent"

    # Mark present, then re-GET → the existing mark is preserved (not reset to absent).
    AttendanceRecord.objects.filter(pk=rec_id).update(status="present")
    body2 = _data(c.get(reverse("attendance:faculty-attendance")))
    assert body2["records"][0]["status"] == "present"
    assert AttendanceRecord.objects.count() == 1  # no duplicate created


def test_requires_faculty():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                          custom_login_id="STU-1", must_change_password=False)
    resp = _client(student).get(reverse("attendance:faculty-attendance"))
    assert resp.status_code == 403


def test_day_mode_class_teacher_sees_day_session():
    """In day-wise mode, the class teacher gets one whole-day session with the roster."""
    from apps.accounts.models.profile import StudentProfile
    from apps.admissions.tests.factories import StudentEnrollmentFactory
    from apps.organizations.models import TenantSettings

    tenant = TenantFactory(institution_type="school")
    TenantSettings.objects.update_or_create(
        tenant=tenant, defaults=dict(attendance_mode="day"))
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                          custom_login_id="FAC-1", must_change_password=False)
    batch = BatchFactory(course__department__branch=branch, academic_year=year,
                         course__name="Class 5", name="A", class_teacher=faculty)
    su = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                     custom_login_id="STU-9", first_name="Rahul", must_change_password=False)
    profile = StudentProfile.objects.create(user=su, current_batch=batch)
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)

    body = _data(_client(faculty).get(reverse("attendance:faculty-attendance")))
    assert len(body["sessions"]) == 1
    s = body["sessions"][0]
    assert s["classLabel"] == "Class 5 - A"
    assert s["subjectName"] == "Day attendance"
    assert len(s["recordIds"]) == 1   # Rahul on the roster
    assert body["records"][0]["status"] == "absent"  # placeholder until marked

    # The class teacher can mark the roster record present.
    rec_id = s["recordIds"][0]
    mark = _client(faculty).patch(
        reverse("attendance:faculty-mark-record", args=[rec_id]),
        {"newStatus": "present"}, format="json")
    assert mark.status_code == 200, mark.content
    assert _data(mark)["record"]["status"] == "present"

    # A different faculty (not the class teacher) is forbidden from marking it.
    other = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                        custom_login_id="FAC-2", must_change_password=False)
    denied = _client(other).patch(
        reverse("attendance:faculty-mark-record", args=[rec_id]),
        {"newStatus": "absent"}, format="json")
    assert denied.status_code == 403
