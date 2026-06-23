"""Faculty invigilation — lists the logged-in faculty's exam duties."""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models import Room
from apps.academics.models.calendar import AcademicPeriod, PeriodType
from apps.academics.models.curriculum import Subject
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.examinations.models import Exam, ExamScheduleSlot, InvigilatorDuty
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def test_faculty_sees_only_their_duties():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    subject = Subject.objects.create(course=batch.course, name="Maths", code="MA")
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type=PeriodType.TERM, sequence=1, name="T1",
        start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 12, 1))
    room = Room.objects.create(branch=branch, name="R1", capacity=40)
    exam = Exam.objects.create(branch=branch, academic_period=period, name="Midterm",
                               exam_fee_paise=0)
    slot = ExamScheduleSlot.objects.create(
        exam=exam, subject=subject, batch=batch, room=room,
        start_at=timezone.now(), end_at=timezone.now() + datetime.timedelta(hours=2),
        max_marks=50)
    me = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                     custom_login_id="FAC-1", first_name="Asha", must_change_password=False)
    other = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                        custom_login_id="FAC-2", must_change_password=False)
    InvigilatorDuty.objects.create(schedule_slot=slot, faculty=me)
    InvigilatorDuty.objects.create(schedule_slot=slot, faculty=other)

    body = _data(_client(me).get(reverse("examinations:faculty-invigilation")))
    assert len(body["assignments"]) == 1
    a = body["assignments"][0]
    assert a["examSlotId"] == str(slot.id)
    assert a["facultyId"] == str(me.id)
    assert "slotLabel" in a
    assert a["assignedBy"] == "manual"
