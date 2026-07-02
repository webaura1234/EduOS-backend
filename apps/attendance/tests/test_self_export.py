"""Request-level tests for the faculty/student self-service attendance exports."""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models import (
    AcademicPeriod, AcademicYear, Batch, BatchSubject, Course, Department, Subject,
)
from apps.academics.models.curriculum import BatchFaculty
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.models import StudentEnrollment
from apps.admissions.queries.enrollment import resolve_enrollment_for_profile
from apps.analytics.enums import ReportStatus
from apps.attendance.enums import AttendanceStatus, SessionStatus
from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.organizations.models import TenantSettings
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
    TenantSettings.objects.create(tenant=tenant, attendance_threshold_percent=75,
                                  exam_day_counts_toward_attendance=True)
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

    session = AttendanceSession.objects.create(
        branch=branch, batch=batch, batch_subject=bs, date=datetime.date(2024, 7, 1),
        status=SessionStatus.COMPLETED, faculty=faculty,
    )
    AttendanceRecord.objects.create(session=session, student=enrollment, status=AttendanceStatus.PRESENT,
                                    marked_at=timezone.now(), marked_by=faculty,
                                    idempotency_key=f"{session.pk}-{enrollment.pk}")
    AttendanceRecord.objects.create(session=session, student=other_enrollment, status=AttendanceStatus.ABSENT,
                                    marked_at=timezone.now(), marked_by=faculty,
                                    idempotency_key=f"{session.pk}-{other_enrollment.pk}")

    return dict(tenant=tenant, branch=branch, batch=batch, faculty=faculty, other_faculty=other_faculty,
               student_user=student_user, enrollment=enrollment,
               other_student_user=other_student_user, other_enrollment=other_enrollment)


def test_faculty_exports_own_subject_attendance(env):
    c = _client(env["faculty"])
    resp = c.post(reverse("attendance:export-my-subject-attendance"), {}, format="json")
    assert resp.status_code == 201, resp.content
    report = _data(resp)["report"]
    assert report["reportType"] == "faculty_subject_attendance"
    assert report["status"] == ReportStatus.READY
    assert report["rowCount"] == 2  # both students' records for the subject they teach


def test_faculty_with_no_assignments_sees_zero_rows(env):
    c = _client(env["other_faculty"])
    resp = c.post(reverse("attendance:export-my-subject-attendance"), {}, format="json")
    report = _data(resp)["report"]
    assert report["rowCount"] == 0


def test_student_exports_own_attendance_only(env):
    c = _client(env["student_user"])
    resp = c.post(reverse("attendance:export-my-attendance"), {}, format="json")
    assert resp.status_code == 201, resp.content
    report = _data(resp)["report"]
    assert report["reportType"] == "student_attendance"
    assert report["status"] == ReportStatus.READY
    assert report["rowCount"] == 1
    assert report["snapshot"]["rows"][0]["status"] == "Present"


def test_student_cannot_see_classmates_attendance(env):
    c = _client(env["other_student_user"])
    resp = c.post(reverse("attendance:export-my-attendance"), {}, format="json")
    report = _data(resp)["report"]
    assert report["rowCount"] == 1
    assert report["snapshot"]["rows"][0]["status"] == "Absent"


def test_admin_cannot_use_faculty_export_endpoint(env):
    admin = UserFactory(role=Role.ADMIN, tenant=env["tenant"], branch=env["branch"],
                        phone="+919800000099", custom_login_id=None, must_change_password=False)
    c = _client(admin)
    resp = c.post(reverse("attendance:export-my-subject-attendance"), {}, format="json")
    assert resp.status_code == 403


def test_faculty_cannot_use_student_export_endpoint(env):
    c = _client(env["faculty"])
    resp = c.post(reverse("attendance:export-my-attendance"), {}, format="json")
    assert resp.status_code == 403
