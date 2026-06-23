"""Student timetable — own class only, never another class's entries."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import PeriodSlot, Timetable, TimetableEntry
from apps.academics.models.calendar import AcademicPeriod, PeriodType
from apps.academics.models.curriculum import BatchSubject, Subject
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


def _slot_entry(branch, year, period, batch, subject_name, code, seq, day):
    subject = Subject.objects.create(course=batch.course, name=subject_name, code=code)
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    slot = PeriodSlot.objects.create(branch=branch, name=f"P{seq}", sequence=seq,
                                     start_time=datetime.time(9, 0), end_time=datetime.time(9, 45))
    tt, _ = Timetable.objects.get_or_create(batch=batch, academic_period=period)
    TimetableEntry.objects.create(timetable=tt, batch_subject=bs, period_slot=slot,
                                  day_of_week=day, status="active")


def test_student_sees_only_own_class_timetable():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type=PeriodType.TERM, sequence=1, name="T1",
        start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 12, 1))

    my_batch = BatchFactory(course__department__branch=branch, academic_year=year,
                            course__name="Class 5", name="A")
    other_batch = BatchFactory(course__department__branch=branch, academic_year=year,
                               course__name="Class 6", name="A")
    _slot_entry(branch, year, period, my_batch, "Maths", "MA5", 1, day=1)
    _slot_entry(branch, year, period, other_batch, "History", "HI6", 2, day=1)  # other class

    su = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                     custom_login_id="STU-1", must_change_password=False)
    profile = StudentProfile.objects.create(user=su, current_batch=my_batch)
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=my_batch)

    body = _data(_client(su).get(reverse("academics:student-timetable")))
    subjects = [p["subjectName"] for d in body["days"] for p in d["periods"]]
    assert subjects == ["Maths"]          # only own class
    assert "History" not in subjects      # other class excluded
