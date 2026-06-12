"""End-to-end tests for marks entry API (Stage 4.4)."""

import datetime
import uuid

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models import AcademicPeriod, AcademicYear, Batch, Course, Department, Room, Subject
from apps.accounts.models.guardian import StudentGuardianLink
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.examinations.enums import MarksStatus
from apps.examinations.models import MarksAudit, MarksEntry

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
def marks_env():
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
        phone="+919800000030",
        custom_login_id=None,
        must_change_password=False,
    )
    faculty = UserFactory(
        role=Role.FACULTY,
        tenant=tenant,
        branch=branch,
        custom_login_id="FAC-M",
        must_change_password=False,
    )
    student_user = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="STU-M-1",
        must_change_password=False,
    )
    student = StudentProfile.objects.create(
        user=student_user, current_batch=batch, academic_status=AcademicStatus.ACTIVE
    )
    from apps.admissions.queries.enrollment import resolve_enrollment_for_profile
    student.enrollment = resolve_enrollment_for_profile(student)
    return dict(
        tenant=tenant,
        branch=branch,
        period=period,
        batch=batch,
        subject=subject,
        room=room,
        admin=admin,
        faculty=faculty,
        student=student,
    )


def _setup_exam_slot_registered(env, client=None, *, marks_deadline=None):
    admin_client = _client(env["admin"])
    exam_payload = {
        "name": "Mid-Term",
        "examType": "midterm",
        "academicPeriodId": str(env["period"].id),
        "examFeePaise": 0,
    }
    if marks_deadline is not None:
        exam_payload["marksDeadline"] = marks_deadline.isoformat()
    exam_id = _data(admin_client.post(reverse("examinations:exam-list"), exam_payload, format="json"))["exam"]["id"]
    slot_id = _data(
        admin_client.post(
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
    admin_client.post(
        reverse("examinations:exam-register", kwargs={"exam_id": exam_id}),
        {"classSectionId": str(env["batch"].id)},
        format="json",
    )
    return exam_id, slot_id


def test_marks_bulk_save_and_submit(marks_env):
    client = _client(marks_env["faculty"])
    _, slot_id = _setup_exam_slot_registered(marks_env)

    save = client.post(
        reverse("examinations:schedule-slot-marks", kwargs={"slot_id": slot_id}),
        {
            "entries": [
                {"studentId": str(marks_env["student"].id), "marks": 85, "isAbsent": False},
            ]
        },
        format="json",
    )
    assert save.status_code == 200, save.content
    entry = _data(save)["entries"][0]
    assert entry["marks"] == 85

    submit = client.post(
        reverse("examinations:schedule-slot-marks-submit", kwargs={"slot_id": slot_id}),
        {},
        format="json",
    )
    assert submit.status_code == 200
    assert _data(submit)["submittedCount"] == 1
    assert MarksEntry.objects.get(pk=entry["id"]).marks_status == MarksStatus.SUBMITTED


def test_marks_over_max_blocked(marks_env):
    client = _client(marks_env["faculty"])
    _, slot_id = _setup_exam_slot_registered(marks_env)
    resp = client.post(
        reverse("examinations:schedule-slot-marks", kwargs={"slot_id": slot_id}),
        {"entries": [{"studentId": str(marks_env["student"].id), "marks": 150}]},
        format="json",
    )
    assert resp.status_code == 400


def test_marks_absent_stored_as_null(marks_env):
    """EC-EXAM-04 — absent stores null marks."""
    client = _client(marks_env["faculty"])
    _, slot_id = _setup_exam_slot_registered(marks_env)
    client.post(
        reverse("examinations:schedule-slot-marks", kwargs={"slot_id": slot_id}),
        {"entries": [{"studentId": str(marks_env["student"].id), "marks": None, "isAbsent": True}]},
        format="json",
    )
    entry = MarksEntry.objects.get(student__student_profile=marks_env["student"])
    assert entry.marks is None
    assert entry.is_absent is True


def test_marks_deadline_blocks_faculty(marks_env):
    past = timezone.now() - datetime.timedelta(hours=1)
    client = _client(marks_env["faculty"])
    _, slot_id = _setup_exam_slot_registered(marks_env, marks_deadline=past)
    resp = client.post(
        reverse("examinations:schedule-slot-marks-submit", kwargs={"slot_id": slot_id}),
        {},
        format="json",
    )
    assert resp.status_code == 403


def test_marks_deadline_admin_override(marks_env):
    past = timezone.now() - datetime.timedelta(hours=1)
    admin_client = _client(marks_env["admin"])
    _, slot_id = _setup_exam_slot_registered(marks_env, marks_deadline=past)
    admin_client.post(
        reverse("examinations:schedule-slot-marks", kwargs={"slot_id": slot_id}),
        {
            "entries": [{"studentId": str(marks_env["student"].id), "marks": 70}],
            "override": True,
            "overrideReason": "Approved late entry",
        },
        format="json",
    )
    resp = admin_client.post(
        reverse("examinations:schedule-slot-marks-submit", kwargs={"slot_id": slot_id}),
        {"override": True, "overrideReason": "Approved late submission"},
        format="json",
    )
    assert resp.status_code == 200
    assert MarksAudit.objects.filter(audit_type="late_submit_override").exists()


def test_marks_version_conflict(marks_env):
    client = _client(marks_env["faculty"])
    _, slot_id = _setup_exam_slot_registered(marks_env)
    save = client.post(
        reverse("examinations:schedule-slot-marks", kwargs={"slot_id": slot_id}),
        {"entries": [{"studentId": str(marks_env["student"].id), "marks": 80}]},
        format="json",
    )
    entry_id = _data(save)["entries"][0]["id"]
    MarksEntry.objects.filter(pk=entry_id).update(version=99)

    conflict = client.patch(
        reverse("examinations:marks-detail", kwargs={"marks_id": entry_id}),
        {"marks": 90, "version": 1},
        format="json",
    )
    assert conflict.status_code == 409


def test_conflict_of_interest_blocked(marks_env):
    group = uuid.uuid4()
    marks_env["faculty"].linked_user_group_id = group
    marks_env["faculty"].save(update_fields=["linked_user_group_id"])
    parent = UserFactory(
        role=Role.PARENT,
        tenant=marks_env["tenant"],
        branch=marks_env["branch"],
        phone="+919800000099",
        linked_user_group_id=group,
        custom_login_id=None,
        must_change_password=False,
    )
    StudentGuardianLink.objects.create(student=marks_env["student"].user, guardian=parent)

    client = _client(marks_env["faculty"])
    _, slot_id = _setup_exam_slot_registered(marks_env)
    blocked = client.post(
        reverse("examinations:schedule-slot-marks", kwargs={"slot_id": slot_id}),
        {"entries": [{"studentId": str(marks_env["student"].id), "marks": 75}]},
        format="json",
    )
    assert blocked.status_code == 403
