"""End-to-end tests for student/parent examination hubs (Stage 4.7)."""

import base64
import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models import AcademicPeriod, AcademicYear, Batch, BatchSubject, Course, Department, Room, Subject
from apps.accounts.models.guardian import StudentGuardianLink
from apps.accounts.models.profile import AcademicStatus, GuardianProfile, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.examinations.models import ExamRegistration

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
def hub_env():
    tenant = TenantFactory(institution_type="college")
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
        period_type="semester",
        sequence=1,
        name="Sem 1",
        start_date=datetime.date(2024, 6, 1),
        end_date=datetime.date(2024, 10, 31),
    )
    dept = Department.objects.create(branch=branch, name="Engg", department_type="stream")
    course = Course.objects.create(department=dept, name="CSE")
    batch = Batch.objects.create(course=course, academic_year=year, name="A")
    subject = Subject.objects.create(course=course, name="Maths", code="MTH", max_marks=100, credits=4)
    BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period, is_required=True)
    room = Room.objects.create(branch=branch, name="Hall A", capacity=40)
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919800000050",
        custom_login_id=None,
        must_change_password=False,
    )
    faculty = UserFactory(
        role=Role.FACULTY,
        tenant=tenant,
        branch=branch,
        custom_login_id="FAC-H",
        must_change_password=False,
    )
    student_user = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="STU-H-1",
        must_change_password=False,
    )
    student = StudentProfile.objects.create(
        user=student_user, current_batch=batch, academic_status=AcademicStatus.ACTIVE
    )
    from apps.admissions.queries.enrollment import resolve_enrollment_for_profile
    student.enrollment = resolve_enrollment_for_profile(student)
    parent_user = UserFactory(
        role=Role.PARENT,
        tenant=tenant,
        branch=branch,
        phone="+919800000051",
        custom_login_id=None,
        must_change_password=False,
    )
    GuardianProfile.objects.create(user=parent_user, relationship_default="father")
    StudentGuardianLink.objects.create(
        student=student_user,
        guardian=parent_user,
        has_portal_access=True,
        is_primary_contact=True,
    )
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
        student_user=student_user,
        parent_user=parent_user,
    )


def _setup_exam_published(env):
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
                "date": (timezone.now() + datetime.timedelta(days=14)).date().isoformat(),
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
        {"entries": [{"studentId": str(env["student"].id), "marks": 80, "isAbsent": False}]},
        format="json",
    )
    faculty.post(reverse("examinations:schedule-slot-marks-submit", kwargs={"slot_id": slot_id}), {}, format="json")
    compute = admin.post(reverse("examinations:exam-results-compute", kwargs={"exam_id": exam_id}), format="json")
    token = _data(compute)["confirmation"]["confirmToken"]
    admin.post(
        reverse("examinations:exam-results-publish", kwargs={"exam_id": exam_id}),
        {"confirmToken": token},
        format="json",
    )
    return exam_id, slot_id


def test_student_exam_hub(hub_env):
    _setup_exam_published(hub_env)
    resp = _client(hub_env["student_user"]).get(reverse("examinations:student-exam-hub"))
    assert resp.status_code == 200, resp.content
    hub = _data(resp)["hub"]
    assert hub["institutionType"] == "college"
    assert hub["student"]["examFeePaid"] is True
    assert hub["hallTicketAvailable"] is True
    assert len(hub["upcomingExams"]) == 1
    assert len(hub["publishedResults"]) == 1
    assert hub["publishedResults"][0]["percent"] == 80.0


def test_student_results_hub(hub_env):
    _setup_exam_published(hub_env)
    resp = _client(hub_env["student_user"]).get(reverse("examinations:student-results-hub"))
    assert resp.status_code == 200
    body = _data(resp)["results"]
    assert body["institutionType"] == "college"
    assert len(body["results"]) == 1
    assert body["results"][0]["percent"] == 80.0


def test_student_assignments_hub(hub_env):
    faculty = _client(hub_env["faculty"])
    faculty.post(
        reverse("examinations:assignment-list"),
        {
            "title": "Homework 1",
            "classSectionId": str(hub_env["batch"].id),
            "subjectId": str(hub_env["subject"].id),
            "dueAt": (timezone.now() + datetime.timedelta(days=5)).isoformat(),
            "maxMarks": 10,
            "academicPeriodId": str(hub_env["period"].id),
        },
        format="json",
    )
    resp = _client(hub_env["student_user"]).get(reverse("examinations:student-assignments-hub"))
    assert resp.status_code == 200
    body = _data(resp)
    assert len(body["assignments"]) == 1
    assert body["submissions"] == []


def test_parent_child_exam_hub(hub_env):
    _setup_exam_published(hub_env)
    resp = _client(hub_env["parent_user"]).get(
        reverse("examinations:parent-child-exam-hub", kwargs={"student_id": str(hub_env["student_user"].id)})
    )
    assert resp.status_code == 200
    assert len(_data(resp)["hub"]["publishedResults"]) == 1


def test_parent_unlinked_child_forbidden(hub_env):
    other_student = UserFactory(
        role=Role.STUDENT,
        tenant=hub_env["tenant"],
        branch=hub_env["branch"],
        custom_login_id="STU-OTHER",
        must_change_password=False,
    )
    resp = _client(hub_env["parent_user"]).get(
        reverse("examinations:parent-child-exam-hub", kwargs={"student_id": str(other_student.id)})
    )
    assert resp.status_code == 403


def test_exam_fee_unpaid_reflected(hub_env):
    admin = _client(hub_env["admin"])
    exam_id = _data(
        admin.post(
            reverse("examinations:exam-list"),
            {
                "name": "Fee Exam",
                "examType": "midterm",
                "academicPeriodId": str(hub_env["period"].id),
                "examFeePaise": 50000,
            },
            format="json",
        )
    )["exam"]["id"]
    admin.post(
        reverse("examinations:exam-register", kwargs={"exam_id": exam_id}),
        {"classSectionId": str(hub_env["batch"].id)},
        format="json",
    )
    reg = ExamRegistration.objects.get(exam_id=exam_id, student__student_profile=hub_env["student"])
    assert reg.fee_paid is False

    resp = _client(hub_env["student_user"]).get(reverse("examinations:student-exam-hub"))
    assert resp.status_code == 200
    assert _data(resp)["hub"]["student"]["examFeePaid"] is False
    assert _data(resp)["hub"]["hallTicketAvailable"] is False
