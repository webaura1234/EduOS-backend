"""End-to-end tests for results API (Stage 4.5)."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import AcademicPeriod, AcademicYear, Batch, Course, Department, Room, Subject
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.examinations.enums import MarksStatus, ResultStatus
from apps.examinations.models import Exam, ResultPublication, StudentResult

from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def _setup_env(*, institution_type="school"):
    tenant = TenantFactory(institution_type=institution_type)
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
        period_type="term" if institution_type == "school" else "semester",
        sequence=1,
        name="Term 1",
        start_date=datetime.date(2024, 6, 1),
        end_date=datetime.date(2024, 10, 31),
    )
    dept = Department.objects.create(branch=branch, name="Science", department_type="stream")
    course = Course.objects.create(department=dept, name="Grade 9")
    batch = Batch.objects.create(course=course, academic_year=year, name="A")
    subject_kwargs = {"course": course, "name": "Maths", "code": "MTH9", "max_marks": 100}
    if institution_type == "college":
        subject_kwargs["credits"] = 4
    subject = Subject.objects.create(**subject_kwargs)
    room = Room.objects.create(branch=branch, name="Hall A", capacity=40)
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919800000040",
        custom_login_id=None,
        must_change_password=False,
    )
    faculty = UserFactory(
        role=Role.FACULTY,
        tenant=tenant,
        branch=branch,
        custom_login_id="FAC-R",
        must_change_password=False,
    )
    student_user = UserFactory(
        role=Role.STUDENT,
        tenant=tenant,
        branch=branch,
        custom_login_id="STU-R-1",
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
        course=course,
        batch=batch,
        subject=subject,
        room=room,
        admin=admin,
        faculty=faculty,
        student=student,
    )


def _setup_exam_with_submitted_marks(env):
    admin_client = _client(env["admin"])
    faculty_client = _client(env["faculty"])
    exam_payload = {
        "name": "Mid-Term",
        "examType": "midterm",
        "academicPeriodId": str(env["period"].id),
        "examFeePaise": 0,
    }
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
    faculty_client.post(
        reverse("examinations:schedule-slot-marks", kwargs={"slot_id": slot_id}),
        {"entries": [{"studentId": str(env["student"].id), "marks": 85, "isAbsent": False}]},
        format="json",
    )
    faculty_client.post(
        reverse("examinations:schedule-slot-marks-submit", kwargs={"slot_id": slot_id}),
        {},
        format="json",
    )
    return exam_id, slot_id


@pytest.fixture
def result_env():
    return _setup_env(institution_type="school")


@pytest.fixture
def college_result_env():
    return _setup_env(institution_type="college")


def test_results_compute_publish_happy_path(result_env):
    admin = _client(result_env["admin"])
    exam_id, _ = _setup_exam_with_submitted_marks(result_env)

    compute = admin.post(reverse("examinations:exam-results-compute", kwargs={"exam_id": exam_id}), format="json")
    assert compute.status_code == 200, compute.content
    confirmation = _data(compute)["confirmation"]
    assert confirmation["confirmToken"]
    assert confirmation["summary"]["totalStudents"] == 1

    publish = admin.post(
        reverse("examinations:exam-results-publish", kwargs={"exam_id": exam_id}),
        {"confirmToken": confirmation["confirmToken"], "note": "Published"},
        format="json",
    )
    assert publish.status_code == 200, publish.content
    body = _data(publish)
    assert body["publication"]["revisionNo"] == 1
    assert body["studentResults"][0]["percentage"] == 85.0

    exam = Exam.objects.get(pk=exam_id)
    assert exam.is_published is True
    assert exam.result_status == ResultStatus.PUBLISHED
    assert ResultPublication.objects.filter(exam_id=exam_id, is_current=True).exists()
    assert StudentResult.objects.filter(exam_id=exam_id).count() == 1

    analytics = admin.get(reverse("examinations:exam-analytics", kwargs={"exam_id": exam_id}))
    assert analytics.status_code == 200
    assert _data(analytics)["analytics"]["averagePercent"] == 85.0


def test_publish_without_confirm_token_blocked(result_env):
    """EC-EXAM-02 — publish without confirm token → 400."""
    admin = _client(result_env["admin"])
    exam_id, _ = _setup_exam_with_submitted_marks(result_env)
    admin.post(reverse("examinations:exam-results-compute", kwargs={"exam_id": exam_id}), format="json")

    resp = admin.post(
        reverse("examinations:exam-results-publish", kwargs={"exam_id": exam_id}),
        {},
        format="json",
    )
    assert resp.status_code == 400


def test_publish_job_in_progress_blocked(result_env):
    """EC-CONCUR-01 — concurrent publish → 409 job_in_progress."""
    admin = _client(result_env["admin"])
    exam_id, _ = _setup_exam_with_submitted_marks(result_env)
    compute = admin.post(reverse("examinations:exam-results-compute", kwargs={"exam_id": exam_id}), format="json")
    token = _data(compute)["confirmation"]["confirmToken"]

    Exam.objects.filter(pk=exam_id).update(publish_in_progress=True)
    resp = admin.post(
        reverse("examinations:exam-results-publish", kwargs={"exam_id": exam_id}),
        {"confirmToken": token},
        format="json",
    )
    assert resp.status_code == 409


def test_revise_published_results(result_env):
    """EC-EXAM-03 — revise creates new publication, never deletes."""
    admin = _client(result_env["admin"])
    exam_id, _ = _setup_exam_with_submitted_marks(result_env)
    compute = admin.post(reverse("examinations:exam-results-compute", kwargs={"exam_id": exam_id}), format="json")
    token = _data(compute)["confirmation"]["confirmToken"]
    admin.post(
        reverse("examinations:exam-results-publish", kwargs={"exam_id": exam_id}),
        {"confirmToken": token},
        format="json",
    )
    first_pub = ResultPublication.objects.get(exam_id=exam_id, is_current=True)

    revise = admin.post(
        reverse("examinations:exam-results-revise", kwargs={"exam_id": exam_id}),
        {"note": "Corrected entry"},
        format="json",
    )
    assert revise.status_code == 200, revise.content
    assert _data(revise)["publication"]["revisionNo"] == 2

    first_pub.refresh_from_db()
    assert first_pub.is_current is False
    assert first_pub.is_revised is True
    assert ResultPublication.objects.filter(exam_id=exam_id).count() == 2


def test_grace_marks_blocked_for_school(result_env):
    """EC-EXAM-07 — grace marks on school → 403."""
    admin = _client(result_env["admin"])
    exam_id, _ = _setup_exam_with_submitted_marks(result_env)
    resp = admin.post(
        reverse("examinations:exam-grace-marks", kwargs={"exam_id": exam_id}),
        {
            "entries": [
                {
                    "studentId": str(result_env["student"].id),
                    "subjectId": str(result_env["subject"].id),
                    "graceMarks": 3,
                }
            ]
        },
        format="json",
    )
    assert resp.status_code == 403


def test_grace_marks_allowed_for_college(college_result_env):
    admin = _client(college_result_env["admin"])
    exam_id, _ = _setup_exam_with_submitted_marks(college_result_env)
    resp = admin.post(
        reverse("examinations:exam-grace-marks", kwargs={"exam_id": exam_id}),
        {
            "entries": [
                {
                    "studentId": str(college_result_env["student"].id),
                    "subjectId": str(college_result_env["subject"].id),
                    "graceMarks": 3,
                }
            ]
        },
        format="json",
    )
    assert resp.status_code == 200, resp.content
    assert _data(resp)["updated"][0]["graceApplied"] == 3.0


def test_college_result_includes_gpa(college_result_env):
    admin = _client(college_result_env["admin"])
    exam_id, _ = _setup_exam_with_submitted_marks(college_result_env)

    # Create grade scale for GPA lookup
    admin.post(
        reverse("examinations:grade-scale-list"),
        {
            "courseId": str(college_result_env["course"].id),
            "name": "Default",
            "bands": [
                {"minPercent": 80, "maxPercent": 100, "grade": "A", "gradePoint": 9},
                {"minPercent": 60, "maxPercent": 79.99, "grade": "B", "gradePoint": 8},
                {"minPercent": 0, "maxPercent": 59.99, "grade": "C", "gradePoint": 6},
            ],
            "isDefault": True,
        },
        format="json",
    )

    compute = admin.post(reverse("examinations:exam-results-compute", kwargs={"exam_id": exam_id}), format="json")
    token = _data(compute)["confirmation"]["confirmToken"]
    publish = admin.post(
        reverse("examinations:exam-results-publish", kwargs={"exam_id": exam_id}),
        {"confirmToken": token},
        format="json",
    )
    assert publish.status_code == 200, publish.content
    result = _data(publish)["studentResults"][0]
    assert result["gpa"] == 9.0
    assert StudentResult.objects.get(exam_id=exam_id).marksheet_key


def test_marks_locked_after_publish(result_env):
    admin = _client(result_env["admin"])
    exam_id, _ = _setup_exam_with_submitted_marks(result_env)
    compute = admin.post(reverse("examinations:exam-results-compute", kwargs={"exam_id": exam_id}), format="json")
    token = _data(compute)["confirmation"]["confirmToken"]
    admin.post(
        reverse("examinations:exam-results-publish", kwargs={"exam_id": exam_id}),
        {"confirmToken": token},
        format="json",
    )
    from apps.examinations.models import MarksEntry

    entry = MarksEntry.objects.get(exam_id=exam_id)
    assert entry.marks_status == MarksStatus.LOCKED


def test_results_preflight(result_env):
    admin = _client(result_env["admin"])
    exam_id, slot_id = _setup_exam_with_submitted_marks(result_env)
    resp = admin.post(
        reverse("examinations:exam-results-preflight", kwargs={"exam_id": exam_id}),
        format="json",
    )
    assert resp.status_code == 200, resp.content
    preflight = _data(resp)["preflight"]
    assert preflight["totalSlots"] >= 1
    assert preflight["canPublish"] is True
    assert any(s["examSlotId"] == str(slot_id) for s in preflight["slots"])


def test_report_card_download_after_publish(result_env):
    admin = _client(result_env["admin"])
    exam_id, _ = _setup_exam_with_submitted_marks(result_env)
    compute = admin.post(reverse("examinations:exam-results-compute", kwargs={"exam_id": exam_id}), format="json")
    token = _data(compute)["confirmation"]["confirmToken"]
    publish = admin.post(
        reverse("examinations:exam-results-publish", kwargs={"exam_id": exam_id}),
        {"confirmToken": token},
        format="json",
    )
    assert publish.status_code == 200, publish.content
    student_id = _data(publish)["studentResults"][0]["studentId"]
    card = admin.get(
        reverse("examinations:exam-report-card", kwargs={"exam_id": exam_id}),
        {"studentId": student_id},
    )
    assert card.status_code == 200, card.content
    payload = _data(card)["reportCard"]
    assert payload["canDownload"] is True
    assert payload["content"]
