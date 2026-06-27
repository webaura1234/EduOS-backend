"""Internal-assessment marks — faculty save + list, with the F-253 deadline rule."""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models.calendar import AcademicPeriod, PeriodType
from apps.academics.models.curriculum import BatchFaculty, BatchSubject, Subject
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.tests.factories import StudentEnrollmentFactory
from apps.examinations.models import InternalMark
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db

MARKS_URL = reverse("examinations:faculty-marks")


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def _assign_subject_teacher(batch, faculty):
    period = AcademicPeriod.objects.create(
        academic_year=batch.academic_year,
        period_type=PeriodType.TERM,
        sequence=1,
        name="T1",
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 12, 1),
    )
    bs = BatchSubject.objects.create(batch=batch, subject=batch._test_subject, academic_period=period)
    BatchFaculty.objects.create(
        batch_subject=bs,
        faculty=faculty,
        role="primary",
        assigned_at=datetime.date(2026, 1, 1),
    )
    return period


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    subject = Subject.objects.create(course=batch.course, name="Maths", code="MA")
    batch._test_subject = subject
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                          custom_login_id="FAC-1", must_change_password=False)
    su = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                     custom_login_id="STU-1", first_name="Ravi", must_change_password=False)
    profile = StudentProfile.objects.create(user=su, current_batch=batch)
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=batch)
    return dict(branch=branch, subject=subject, faculty=faculty, profile=profile, tenant=tenant, batch=batch)


@pytest.fixture
def college_env(env):
    env["tenant"].institution_type = "college"
    env["tenant"].save(update_fields=["institution_type"])
    _assign_subject_teacher(env["batch"], env["faculty"])
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
    assert _data(resp)["mark"]["classLabel"]

    body = _data(_client(env["faculty"]).get(MARKS_URL))
    assert body["myClass"]["canEdit"] is False
    assert body["classesITeach"]["canEdit"] is True
    assert body["classesITeach"]["examSlots"] == [] and body["classesITeach"]["examEntries"] == []
    assert len(body["classesITeach"]["internal"]) == 1
    assert body["classesITeach"]["internal"][0]["subjectName"] == "Maths"


def test_exam_slots_and_entries_for_taught_subject(college_env):
    env = college_env
    from apps.academics.models import Room
    from apps.examinations.models import Exam, ExamScheduleSlot, MarksEntry

    branch, subject, faculty, profile = (
        env["branch"], env["subject"], env["faculty"], env["profile"],
    )
    batch = profile.current_batch
    period = BatchSubject.objects.filter(batch=batch, subject=subject).first().academic_period
    room = Room.objects.create(branch=branch, name="R1", capacity=40)
    exam = Exam.objects.create(
        branch=branch, academic_period=period, name="Midterm",
        exam_fee_paise=0,
        marks_deadline=timezone.now() + datetime.timedelta(days=5),
    )
    slot = ExamScheduleSlot.objects.create(
        exam=exam, subject=subject, batch=batch, room=room,
        start_at=timezone.now(), end_at=timezone.now() + datetime.timedelta(hours=2),
        max_marks=50,
    )
    enrollment = profile.enrollments.first()
    MarksEntry.objects.create(exam=exam, subject=subject, student=enrollment, marks=42)

    body = _data(_client(faculty).get(MARKS_URL))
    teach = body["classesITeach"]
    assert len(teach["examSlots"]) == 1
    assert teach["examSlots"][0]["entryLocked"] is False
    assert len(teach["examEntries"]) == 1
    assert teach["examEntries"][0]["marks"] == 42.0
    assert teach["examEntries"][0]["examSlotId"] == str(slot.id)


def test_class_teacher_sees_homeroom_exam_marks_read_only(college_env):
    env = college_env
    from apps.academics.models import Room
    from apps.examinations.models import Exam, ExamScheduleSlot, MarksEntry

    homeroom = env["batch"]
    other_batch = BatchFactory(
        course__department__branch=env["branch"],
        academic_year=homeroom.academic_year,
        name="B",
    )
    class_teacher = UserFactory(
        role=Role.FACULTY, tenant=env["tenant"], branch=env["branch"],
        custom_login_id="FAC-CT", must_change_password=False,
    )
    homeroom.class_teacher = class_teacher
    homeroom.save(update_fields=["class_teacher"])

    subject_teacher = env["faculty"]
    other_subject = Subject.objects.create(course=other_batch.course, name="Science", code="SC")
    other_batch._test_subject = other_subject
    period = _assign_subject_teacher(other_batch, subject_teacher)

    room = Room.objects.create(branch=env["branch"], name="R2", capacity=40)
    exam = Exam.objects.create(
        branch=env["branch"], academic_period=period, name="Unit test",
        exam_fee_paise=0,
        marks_deadline=timezone.now() + datetime.timedelta(days=5),
    )
    ExamScheduleSlot.objects.create(
        exam=exam, subject=other_subject, batch=homeroom, room=room,
        start_at=timezone.now(), end_at=timezone.now() + datetime.timedelta(hours=2),
        max_marks=50,
    )
    enrollment = env["profile"].enrollments.first()
    MarksEntry.objects.create(exam=exam, subject=other_subject, student=enrollment, marks=38)

    body = _data(_client(class_teacher).get(MARKS_URL))
    assert body["myClass"]["canEdit"] is False
    assert len(body["myClass"]["homerooms"]) == 1
    assert len(body["myClass"]["examEntries"]) == 1
    assert body["myClass"]["examEntries"][0]["marks"] == 38.0
    assert body["classesITeach"]["examSlots"] == []


def test_deadline_blocks_faculty_but_admin_overrides(college_env):
    env = college_env
    InternalMark.objects.create(
        branch=env["branch"], student_profile=env["profile"], subject=env["subject"],
        marks=10, max_marks=20, recorded_by=env["faculty"],
        hard_deadline_at=timezone.now() - datetime.timedelta(days=1),
    )
    save_url = reverse("examinations:faculty-internal-marks-save")
    payload = {
        "studentId": str(env["profile"].id), "subjectId": str(env["subject"].id),
        "marks": 19, "maxMarks": 20,
    }

    resp = _client(env["faculty"]).post(save_url, payload, format="json")
    assert resp.status_code == 400
    assert "deadline" in resp.content.decode().lower()

    admin = UserFactory(
        role=Role.ADMIN, tenant=env["branch"].tenant, branch=env["branch"],
        phone="+919810000001", custom_login_id=None, must_change_password=False,
    )
    resp = _client(admin).post(save_url, payload, format="json")
    assert resp.status_code == 201, resp.content
    assert _data(resp)["mark"]["marks"] == 19.0


def test_school_faculty_marks_list_omits_internal(env):
    InternalMark.objects.create(
        branch=env["branch"], student_profile=env["profile"], subject=env["subject"],
        marks=12, max_marks=20, recorded_by=env["faculty"],
    )
    body = _data(_client(env["faculty"]).get(MARKS_URL))
    assert body["myClass"]["internal"] == []
    assert body["classesITeach"]["internal"] == []


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
