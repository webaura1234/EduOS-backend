"""Faculty study materials (Notes) — list own uploads + teaching slots, record upload."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models.calendar import AcademicPeriod, PeriodType
from apps.academics.models.curriculum import BatchSubject, Subject
from apps.academics.models.timetable import (
    PeriodSlot, Timetable, TimetableEntry,
)
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


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    subject = Subject.objects.create(course=batch.course, name="Maths", code="MA")
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type=PeriodType.TERM, sequence=1, name="T1",
        start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 12, 1))
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    slot = PeriodSlot.objects.create(branch=branch, name="Period 1", sequence=1,
                                     start_time=datetime.time(9, 0),
                                     end_time=datetime.time(9, 45))
    tt = Timetable.objects.create(batch=batch, academic_period=period, is_published=True)
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                          custom_login_id="FAC-1", must_change_password=False)
    entry = TimetableEntry.objects.create(
        timetable=tt, batch_subject=bs, period_slot=slot, day_of_week=1, faculty=faculty)
    return dict(branch=branch, faculty=faculty, entry=entry)


def test_lists_teaching_slots(env):
    body = _data(_client(env["faculty"]).get(reverse("academics:faculty-materials")))
    assert body["materials"] == []
    assert len(body["uploadSessions"]) == 1
    s = body["uploadSessions"][0]
    assert s["timetableSlotId"] == str(env["entry"].id)
    assert s["subjectName"] == "Maths" and s["dayOfWeek"] == 1 and s["periodIndex"] == 1


def test_upload_then_list_material(env):
    url = reverse("academics:faculty-materials")
    resp = _client(env["faculty"]).post(url, {
        "timetableSlotId": str(env["entry"].id), "sessionDate": "2026-06-22",
        "fileName": "algebra-notes.pdf",
    }, format="json")
    assert resp.status_code == 201, resp.content
    assert _data(resp)["fileName"] == "algebra-notes.pdf"

    body = _data(_client(env["faculty"]).get(url))
    assert len(body["materials"]) == 1
    assert body["materials"][0]["timetableSlotId"] == str(env["entry"].id)
