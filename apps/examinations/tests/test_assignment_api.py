"""End-to-end tests for assignments API (Stage 4.6)."""

import base64
import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models import AcademicPeriod, AcademicYear, Batch, BatchSubject, Course, Department, Subject
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.examinations.enums import SubmissionStatus
from apps.examinations.models import Assignment, AssignmentSubmission

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
def assignment_env():
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
    BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period, is_required=True)
    faculty = UserFactory(
        role=Role.FACULTY,
        tenant=tenant,
        branch=branch,
        custom_login_id="FAC-A",
        must_change_password=False,
    )
    student_user = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="STU-A-1",
        must_change_password=False,
    )
    student = StudentProfile.objects.create(
        user=student_user, current_batch=batch, academic_status=AcademicStatus.ACTIVE
    )
    return dict(
        tenant=tenant,
        branch=branch,
        period=period,
        batch=batch,
        subject=subject,
        faculty=faculty,
        student=student,
        student_user=student_user,
    )


def _due_at_future():
    return (timezone.now() + datetime.timedelta(days=7)).isoformat()


def _create_assignment(env, client=None):
    client = client or _client(env["faculty"])
    resp = client.post(
        reverse("examinations:assignment-list"),
        {
            "title": "Algebra Worksheet",
            "description": "Complete exercises 1-10",
            "classSectionId": str(env["batch"].id),
            "subjectId": str(env["subject"].id),
            "dueAt": _due_at_future(),
            "maxMarks": 25,
            "academicPeriodId": str(env["period"].id),
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return _data(resp)["assignment"]["id"]


def test_assignment_create_list_submit_grade(assignment_env):
    faculty = _client(assignment_env["faculty"])
    student = _client(assignment_env["student_user"])
    assignment_id = _create_assignment(assignment_env, faculty)

    listed = faculty.get(reverse("examinations:assignment-list"))
    assert listed.status_code == 200
    body = _data(listed)
    assert len(body["assignments"]) == 1
    assert body["assignments"][0]["title"] == "Algebra Worksheet"

    content = base64.b64encode(b"sample homework file").decode("ascii")
    submit = student.post(
        reverse("examinations:assignment-submit", kwargs={"assignment_id": assignment_id}),
        {"fileName": "worksheet.pdf", "fileContent": content},
        format="json",
    )
    assert submit.status_code == 200, submit.content
    submission_id = _data(submit)["submission"]["id"]
    assert _data(submit)["submission"]["submissionStatus"] == SubmissionStatus.SUBMITTED

    grade = faculty.patch(
        reverse("examinations:submission-grade", kwargs={"submission_id": submission_id}),
        {"gradedMarks": 22},
        format="json",
    )
    assert grade.status_code == 200, grade.content
    assert _data(grade)["submission"]["gradedMarks"] == 22.0
    assert AssignmentSubmission.objects.get(pk=submission_id).submission_status == SubmissionStatus.GRADED


def test_late_submission_marked(assignment_env):
    faculty = _client(assignment_env["faculty"])
    student = _client(assignment_env["student_user"])
    due_past = timezone.now() - datetime.timedelta(hours=1)
    resp = faculty.post(
        reverse("examinations:assignment-list"),
        {
            "title": "Late Task",
            "classSectionId": str(assignment_env["batch"].id),
            "subjectId": str(assignment_env["subject"].id),
            "dueAt": (timezone.now() + datetime.timedelta(days=1)).isoformat(),
            "maxMarks": 10,
            "academicPeriodId": str(assignment_env["period"].id),
        },
        format="json",
    )
    assignment_id = _data(resp)["assignment"]["id"]
    Assignment.objects.filter(pk=assignment_id).update(due_at=due_past)

    submit = student.post(
        reverse("examinations:assignment-submit", kwargs={"assignment_id": assignment_id}),
        {
            "fileName": "late.pdf",
            "fileContent": base64.b64encode(b"late").decode("ascii"),
        },
        format="json",
    )
    assert submit.status_code == 200
    assert _data(submit)["submission"]["submissionStatus"] == SubmissionStatus.LATE


def test_grade_over_max_blocked(assignment_env):
    faculty = _client(assignment_env["faculty"])
    student = _client(assignment_env["student_user"])
    assignment_id = _create_assignment(assignment_env, faculty)
    submit = student.post(
        reverse("examinations:assignment-submit", kwargs={"assignment_id": assignment_id}),
        {
            "fileName": "work.pdf",
            "fileContent": base64.b64encode(b"x").decode("ascii"),
        },
        format="json",
    )
    submission_id = _data(submit)["submission"]["id"]
    grade = faculty.patch(
        reverse("examinations:submission-grade", kwargs={"submission_id": submission_id}),
        {"gradedMarks": 99},
        format="json",
    )
    assert grade.status_code == 400


def test_student_cannot_grade(assignment_env):
    faculty = _client(assignment_env["faculty"])
    student = _client(assignment_env["student_user"])
    assignment_id = _create_assignment(assignment_env, faculty)
    submit = student.post(
        reverse("examinations:assignment-submit", kwargs={"assignment_id": assignment_id}),
        {
            "fileName": "work.pdf",
            "fileContent": base64.b64encode(b"x").decode("ascii"),
        },
        format="json",
    )
    submission_id = _data(submit)["submission"]["id"]
    resp = student.patch(
        reverse("examinations:submission-grade", kwargs={"submission_id": submission_id}),
        {"gradedMarks": 20},
        format="json",
    )
    assert resp.status_code == 403


def test_graded_submission_cannot_be_replaced(assignment_env):
    faculty = _client(assignment_env["faculty"])
    student = _client(assignment_env["student_user"])
    assignment_id = _create_assignment(assignment_env, faculty)
    submit = student.post(
        reverse("examinations:assignment-submit", kwargs={"assignment_id": assignment_id}),
        {
            "fileName": "work.pdf",
            "fileContent": base64.b64encode(b"x").decode("ascii"),
        },
        format="json",
    )
    submission_id = _data(submit)["submission"]["id"]
    faculty.patch(
        reverse("examinations:submission-grade", kwargs={"submission_id": submission_id}),
        {"gradedMarks": 20},
        format="json",
    )
    resubmit = student.post(
        reverse("examinations:assignment-submit", kwargs={"assignment_id": assignment_id}),
        {
            "fileName": "work2.pdf",
            "fileContent": base64.b64encode(b"y").decode("ascii"),
        },
        format="json",
    )
    assert resubmit.status_code == 400
