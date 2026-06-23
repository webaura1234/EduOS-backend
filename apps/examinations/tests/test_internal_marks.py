"""Internal-assessment marks — faculty save + list, with the F-253 deadline rule."""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models.curriculum import Subject
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.tests.factories import StudentEnrollmentFactory
from apps.examinations.models import InternalMark
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
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                          custom_login_id="FAC-1", must_change_password=False)
    su = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                     custom_login_id="STU-1", first_name="Ravi", must_change_password=False)
    profile = StudentProfile.objects.create(user=su, current_batch=batch)
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)
    return dict(branch=branch, subject=subject, faculty=faculty, profile=profile, tenant=tenant)


@pytest.fixture
def college_env(env):
    env["tenant"].institution_type = "college"
    env["tenant"].save(update_fields=["institution_type"])
    return env


def test_save_and_list_internal_mark(college_env):
    env = college_env
    save_url = reverse("examinations:faculty-internal-marks-save")
    resp = _client(env["faculty"]).post(save_url, {
        "studentId": str(env["profile"].id), "subjectId": str(env["subject"].id),
        "marks": 18, "maxMarks": 20,
    }, format="json")
    assert resp.status_code == 201, resp.content
    assert _data(resp)["mark"]["marks"] == 18.0
    assert _data(resp)["mark"]["classLabel"]  # resolved from enrollment

    body = _data(_client(env["faculty"]).get(reverse("examinations:faculty-marks")))
    assert body["examSlots"] == [] and body["examEntries"] == []
    assert len(body["internal"]) == 1
    assert body["internal"][0]["subjectName"] == "Maths"


def test_exam_slots_and_entries_for_taught_subject(college_env):
    env = college_env
    from apps.academics.models import Room
    from apps.academics.models.calendar import AcademicPeriod, PeriodType
    from apps.academics.models.curriculum import BatchFaculty, BatchSubject
    from apps.examinations.models import Exam, ExamScheduleSlot, MarksEntry

    branch, subject, faculty, profile = (env["branch"], env["subject"],
                                         env["faculty"], env["profile"])
    batch = profile.current_batch
    year = batch.academic_year
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type=PeriodType.TERM, sequence=1, name="T1",
        start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 12, 1))
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    BatchFaculty.objects.create(batch_subject=bs, faculty=faculty, role="primary",
                                assigned_at=datetime.date(2026, 1, 1))
    room = Room.objects.create(branch=branch, name="R1", capacity=40)
    exam = Exam.objects.create(branch=branch, academic_period=period, name="Midterm",
                               exam_fee_paise=0,
                               marks_deadline=timezone.now() + datetime.timedelta(days=5))
    slot = ExamScheduleSlot.objects.create(
        exam=exam, subject=subject, batch=batch, room=room,
        start_at=timezone.now(), end_at=timezone.now() + datetime.timedelta(hours=2),
        max_marks=50)
    enrollment = profile.enrollments.first()
    MarksEntry.objects.create(exam=exam, subject=subject, student=enrollment, marks=42)

    body = _data(_client(faculty).get(reverse("examinations:faculty-marks")))
    assert len(body["examSlots"]) == 1
    assert body["examSlots"][0]["entryLocked"] is False
    assert len(body["examEntries"]) == 1
    assert body["examEntries"][0]["marks"] == 42.0
    assert body["examEntries"][0]["examSlotId"] == str(slot.id)


def test_deadline_blocks_faculty_but_admin_overrides(college_env):
    env = college_env
    InternalMark.objects.create(
        branch=env["branch"], student_profile=env["profile"], subject=env["subject"],
        marks=10, max_marks=20, recorded_by=env["faculty"],
        hard_deadline_at=timezone.now() - datetime.timedelta(days=1),
    )
    save_url = reverse("examinations:faculty-internal-marks-save")
    payload = {"studentId": str(env["profile"].id), "subjectId": str(env["subject"].id),
               "marks": 19, "maxMarks": 20}

    # Faculty blocked past the deadline.
    resp = _client(env["faculty"]).post(save_url, payload, format="json")
    assert resp.status_code == 400
    assert "deadline" in resp.content.decode().lower()

    # Admin overrides.
    admin = UserFactory(role=Role.ADMIN, tenant=env["branch"].tenant, branch=env["branch"],
                        phone="+919810000001", custom_login_id=None, must_change_password=False)
    resp = _client(admin).post(save_url, payload, format="json")
    assert resp.status_code == 201, resp.content
    assert _data(resp)["mark"]["marks"] == 19.0


def test_school_faculty_marks_list_omits_internal(env):
    InternalMark.objects.create(
        branch=env["branch"], student_profile=env["profile"], subject=env["subject"],
        marks=12, max_marks=20, recorded_by=env["faculty"],
    )
    body = _data(_client(env["faculty"]).get(reverse("examinations:faculty-marks")))
    assert body["internal"] == []


def test_school_internal_mark_save_rejected(env):
    save_url = reverse("examinations:faculty-internal-marks-save")
    resp = _client(env["faculty"]).post(save_url, {
        "studentId": str(env["profile"].id),
        "subjectId": str(env["subject"].id),
        "marks": 18,
        "maxMarks": 20,
    }, format="json")
    assert resp.status_code == 403
    assert "school" in resp.content.decode().lower()
