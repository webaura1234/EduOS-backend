"""EC-DATA-02 / F-096 — subject delete blocked when marks exist; archive allowed."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import AcademicPeriod, AcademicYear, Batch, Course, Department, Room, Subject
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.examinations.models import MarksEntry

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
def archive_guard_env():
    tenant = TenantFactory(institution_type="school")
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
    subject = Subject.objects.create(course=course, name="Maths", code="MTH9", max_marks=100)
    room = Room.objects.create(branch=branch, name="Hall A", capacity=40)
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919800000060",
        custom_login_id=None,
        must_change_password=False,
    )
    faculty = UserFactory(
        role=Role.FACULTY,
        tenant=tenant,
        branch=branch,
        custom_login_id="FAC-AG",
        must_change_password=False,
    )
    student_user = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="STU-AG-1",
        must_change_password=False,
    )
    student = StudentProfile.objects.create(
        user=student_user, current_batch=batch, academic_status=AcademicStatus.ACTIVE
    )
    from apps.admissions.queries.enrollment import resolve_enrollment_for_profile
    resolve_enrollment_for_profile(student)
    return dict(
        tenant=tenant,
        branch=branch,
        period=period,
        course=course,
        batch=batch,
        subject=subject,
        room=room,
        admin=admin,
        faculty=faculty,
        student=student,
    )


def _create_marks_for_subject(env):
    admin = _client(env["admin"])
    faculty = _client(env["faculty"])
    exam_id = _data(
        admin.post(
            reverse("examinations:exam-list"),
            {
                "name": "Mid-Term",
                "examType": "midterm",
                "academicPeriodId": str(env["period"].id),
                "examFeePaise": 0,
            },
            format="json",
        )
    )["exam"]["id"]
    slot_id = _data(
        admin.post(
            reverse("examinations:exam-schedule-list", kwargs={"exam_id": exam_id}),
            {
                "classSectionId": str(env["batch"].id),
                "subjectId": str(env["subject"].id),
                "date": "2024-09-15",
                "startTime": "09:00",
                "endTime": "11:00",
                "roomId": str(env["room"].id),
                "override": True,
            },
            format="json",
        )
    )["slot"]["id"]
    admin.post(
        reverse("examinations:exam-register", kwargs={"exam_id": exam_id}),
        {"classSectionId": str(env["batch"].id)},
        format="json",
    )
    faculty.post(
        reverse("examinations:schedule-slot-marks", kwargs={"slot_id": slot_id}),
        {"entries": [{"studentId": str(env["student"].id), "marks": 70, "isAbsent": False}]},
        format="json",
    )
    assert MarksEntry.objects.filter(subject_id=env["subject"].id).exists()


def test_subject_delete_without_marks(archive_guard_env):
    admin = _client(archive_guard_env["admin"])
    subject_id = archive_guard_env["subject"].id
    resp = admin.delete(reverse("academics:subject-detail", kwargs={"subject_id": subject_id}))
    assert resp.status_code == 200
    assert Subject.objects.filter(pk=subject_id, is_active=False).exists()


def test_subject_delete_blocked_when_marks_exist(archive_guard_env):
    """EC-DATA-02 — delete returns 409 when marks exist."""
    _create_marks_for_subject(archive_guard_env)
    admin = _client(archive_guard_env["admin"])
    subject_id = archive_guard_env["subject"].id
    resp = admin.delete(reverse("academics:subject-detail", kwargs={"subject_id": subject_id}))
    assert resp.status_code == 409
    body = resp.json()
    assert body["errors"]["hasMarks"] is True
    assert body["errors"]["code"] == "subject_has_marks"
    assert Subject.objects.filter(pk=subject_id, is_active=True).exists()


def test_subject_archive_allowed_when_marks_exist(archive_guard_env):
    """EC-DATA-02 — archive (soft-delete) succeeds when marks exist."""
    _create_marks_for_subject(archive_guard_env)
    admin = _client(archive_guard_env["admin"])
    subject_id = archive_guard_env["subject"].id
    resp = admin.post(reverse("academics:subject-archive", kwargs={"subject_id": subject_id}))
    assert resp.status_code == 200, resp.content
    assert _data(resp)["archived"] is True
    assert Subject.objects.filter(pk=subject_id, is_active=False).exists()
    assert MarksEntry.objects.filter(subject_id=subject_id).exists()


def test_list_archived_subjects(archive_guard_env):
    _create_marks_for_subject(archive_guard_env)
    admin = _client(archive_guard_env["admin"])
    subject_id = archive_guard_env["subject"].id
    admin.post(reverse("academics:subject-archive", kwargs={"subject_id": subject_id}))

    active = _data(admin.get(reverse("academics:subjects")))["subjects"]
    archived = _data(admin.get(reverse("academics:subjects"), {"archived": "true"}))["subjects"]
    assert all(str(s["id"]) != str(subject_id) for s in active)
    assert any(str(s["id"]) == str(subject_id) for s in archived)
