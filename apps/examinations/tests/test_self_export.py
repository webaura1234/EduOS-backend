"""Request-level tests for the faculty class-results and student exam-results self-exports."""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models import AcademicPeriod, AcademicYear, Batch, BatchSubject, Course, Department, Subject
from apps.academics.models.curriculum import BatchFaculty
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.queries.enrollment import resolve_enrollment_for_profile
from apps.analytics.enums import ReportStatus
from apps.examinations.enums import MarksStatus
from apps.examinations.models.exam import Exam
from apps.examinations.models.results import MarksEntry, ResultPublication, StudentResult
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
    year = AcademicYear.objects.create(branch=branch, name="2024-25", is_current=True,
                                       start_date=datetime.date(2024, 6, 1), end_date=datetime.date(2025, 4, 30))
    period = AcademicPeriod.objects.create(academic_year=year, period_type="term", sequence=1,
                                           name="Term 1", start_date=datetime.date(2024, 6, 1),
                                           end_date=datetime.date(2024, 10, 31))
    dept = Department.objects.create(branch=branch, name="Science", department_type="stream")
    course = Course.objects.create(department=dept, name="Grade 9")
    batch = Batch.objects.create(course=course, academic_year=year, name="A")
    subject = Subject.objects.create(course=course, name="Maths", code="MTH9")
    other_subject = Subject.objects.create(course=course, name="Science", code="SCI9")
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)

    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch, custom_login_id="FAC-1",
                          must_change_password=False)
    BatchFaculty.objects.create(batch_subject=bs, faculty=faculty, role="primary",
                                assigned_at=datetime.date(2024, 6, 1))

    other_faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch, custom_login_id="FAC-2",
                                must_change_password=False)

    student_user = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-1",
                               must_change_password=False)
    profile = StudentProfile.objects.create(user=student_user, current_batch=batch,
                                            academic_status=AcademicStatus.ACTIVE)
    enrollment = resolve_enrollment_for_profile(profile)

    other_student_user = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-2",
                                     must_change_password=False)
    other_profile = StudentProfile.objects.create(user=other_student_user, current_batch=batch,
                                                  academic_status=AcademicStatus.ACTIVE)
    other_enrollment = resolve_enrollment_for_profile(other_profile)

    exam = Exam.objects.create(branch=branch, academic_period=period, name="Mid-Term",
                               marks_deadline=timezone.now() + datetime.timedelta(days=1))

    # faculty's own subject — should be visible in their export
    MarksEntry.objects.create(exam=exam, subject=subject, student=enrollment, marks=45, marks_status=MarksStatus.SUBMITTED)
    # a DIFFERENT subject that faculty does not teach — must not leak into their export
    MarksEntry.objects.create(exam=exam, subject=other_subject, student=enrollment, marks=30, marks_status=MarksStatus.SUBMITTED)

    # published overall result for the primary student (visible to them)
    publication = ResultPublication.objects.create(exam=exam, published_at=timezone.now(), snapshot_hash="abc123")
    StudentResult.objects.create(exam=exam, student=enrollment, publication=publication,
                                 total_marks=75, percentage=75, grade="A", is_pass=True)
    # unpublished result for the other student — must not be exportable
    StudentResult.objects.create(exam=exam, student=other_enrollment, publication=None,
                                 total_marks=40, percentage=40, grade="C", is_pass=True)

    return dict(tenant=tenant, branch=branch, exam=exam, faculty=faculty, other_faculty=other_faculty,
               student_user=student_user, other_student_user=other_student_user)


def test_faculty_exports_only_own_subject_marks(env):
    c = _client(env["faculty"])
    resp = c.post(reverse("examinations:faculty-export-class-results"), {}, format="json")
    assert resp.status_code == 201, resp.content
    report = _data(resp)["report"]
    assert report["reportType"] == "faculty_class_results"
    assert report["status"] == ReportStatus.READY
    assert report["rowCount"] == 1  # only the Maths entry, not Science
    assert report["snapshot"]["rows"][0]["subject"] == "Maths"


def test_faculty_with_no_assignments_sees_zero_marks(env):
    c = _client(env["other_faculty"])
    resp = c.post(reverse("examinations:faculty-export-class-results"), {}, format="json")
    report = _data(resp)["report"]
    assert report["rowCount"] == 0


def test_student_exports_own_published_results(env):
    c = _client(env["student_user"])
    resp = c.post(reverse("examinations:student-export-results"), {}, format="json")
    assert resp.status_code == 201, resp.content
    report = _data(resp)["report"]
    assert report["reportType"] == "student_exam_results"
    assert report["status"] == ReportStatus.READY
    assert report["rowCount"] == 1
    assert report["snapshot"]["rows"][0]["grade"] == "A"


def test_student_with_unpublished_result_sees_nothing(env):
    c = _client(env["other_student_user"])
    resp = c.post(reverse("examinations:student-export-results"), {}, format="json")
    report = _data(resp)["report"]
    assert report["rowCount"] == 0


def test_admin_cannot_use_faculty_results_export_endpoint(env):
    admin = UserFactory(role=Role.ADMIN, tenant=env["tenant"], branch=env["branch"],
                        phone="+919800000098", custom_login_id=None, must_change_password=False)
    c = _client(admin)
    resp = c.post(reverse("examinations:faculty-export-class-results"), {}, format="json")
    assert resp.status_code == 403


def test_faculty_cannot_use_student_results_export_endpoint(env):
    c = _client(env["faculty"])
    resp = c.post(reverse("examinations:student-export-results"), {}, format="json")
    assert resp.status_code == 403
