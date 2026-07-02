"""Request-level tests for the attendance async CSV export endpoints."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import (
    AcademicPeriod, AcademicYear, Batch, BatchSubject, Course, Department, Subject,
)
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.models import StudentEnrollment
from apps.analytics.enums import ReportStatus
from apps.organizations.models import TenantSettings
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    """StandardJSONRenderer wraps every response as {"data": {...}}."""
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
    BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919800000001",
                        custom_login_id=None, must_change_password=False)
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch, custom_login_id="FAC-1",
                          must_change_password=False)
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-1",
                          must_change_password=False)
    profile = StudentProfile.objects.create(user=student, current_batch=batch, academic_status=AcademicStatus.ACTIVE)
    StudentEnrollment.objects.create(branch=branch, student_profile=profile, batch=batch, academic_year=year)
    return dict(tenant=tenant, branch=branch, year=year, batch=batch, admin=admin, faculty=faculty, student=student)


def test_monthly_export_creates_ready_report(env):
    c = _client(env["admin"])
    resp = c.post(reverse("attendance:export-monthly"), {"year": 2024, "month": 7}, format="json")
    assert resp.status_code == 201, resp.content
    report = _data(resp)["report"]
    assert report["reportType"] == "attendance_monthly"
    assert report["status"] == ReportStatus.READY


def test_shortage_export_creates_ready_report(env):
    c = _client(env["admin"])
    resp = c.post(reverse("attendance:export-shortage"), {}, format="json")
    assert resp.status_code == 201, resp.content
    report = _data(resp)["report"]
    assert report["reportType"] == "attendance_shortage"
    assert report["status"] == ReportStatus.READY


def test_ranking_export_creates_ready_report(env):
    c = _client(env["admin"])
    resp = c.post(reverse("attendance:export-ranking"), {}, format="json")
    assert resp.status_code == 201, resp.content
    report = _data(resp)["report"]
    assert report["reportType"] == "attendance_ranking"
    assert report["status"] == ReportStatus.READY


def test_detention_export_creates_ready_report(env):
    c = _client(env["admin"])
    resp = c.post(reverse("attendance:export-detention"), {}, format="json")
    assert resp.status_code == 201, resp.content
    report = _data(resp)["report"]
    assert report["reportType"] == "attendance_detention"
    assert report["status"] == ReportStatus.READY


def test_export_endpoints_reject_students(env):
    c = _client(env["student"])
    resp = c.post(reverse("attendance:export-monthly"), {"year": 2024, "month": 7}, format="json")
    assert resp.status_code == 403


def test_export_endpoints_reject_faculty(env):
    c = _client(env["faculty"])
    resp = c.post(reverse("attendance:export-shortage"), {}, format="json")
    assert resp.status_code == 403


def test_exported_report_is_downloadable_via_analytics_endpoint(env):
    c = _client(env["admin"])
    resp = c.post(reverse("attendance:export-monthly"), {"year": 2024, "month": 7}, format="json")
    export_id = _data(resp)["report"]["id"]

    download = c.get(f"/api/v1/analytics/reports/{export_id}/download/")
    assert download.status_code == 200, download.content
