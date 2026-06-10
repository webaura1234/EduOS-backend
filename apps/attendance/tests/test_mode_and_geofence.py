"""Tests for per-school day-wise mode and backend geo-fence validation."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import (
    AcademicPeriod, AcademicYear, Batch, BatchSubject, Course, Department, PeriodSlot, Subject,
)
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.attendance.enums import AttendanceStatus
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


def _build(*, attendance_mode="session", lat=None, lng=None, radius=None):
    tenant = TenantFactory(institution_type="school")
    TenantSettings.objects.create(tenant=tenant, attendance_mode=attendance_mode)
    branch = BranchFactory(tenant=tenant, latitude=lat, longitude=lng, geofence_radius_m=radius)
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
    slot = PeriodSlot.objects.create(branch=branch, name="Period 1", sequence=1,
                                     start_time=datetime.time(9, 0), end_time=datetime.time(9, 45))
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch, custom_login_id="FAC-1",
                          must_change_password=False)
    s1 = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-1",
                     must_change_password=False)
    p1 = StudentProfile.objects.create(user=s1, current_batch=batch, academic_status=AcademicStatus.ACTIVE)
    return dict(branch=branch, batch=batch, bs=bs, slot=slot, faculty=faculty, p1=p1)


# ── Day-wise mode ─────────────────────────────────────────────────────────────
def test_day_mode_marking(env=None):
    e = _build(attendance_mode="day")
    c = _client(e["faculty"])
    # Day mode: open with batchId only (no subject/slot).
    resp = c.post(reverse("attendance:session-open"),
                  {"batchId": str(e["batch"].id), "date": datetime.date.today().isoformat()}, format="json")
    assert resp.status_code == 201, resp.content
    sid = _data(resp)["session"]["id"]
    session = AttendanceSession.objects.get(pk=sid)
    assert session.mode == "day"
    assert session.batch_subject_id is None and session.period_slot_id is None

    mark = c.post(reverse("attendance:session-mark", kwargs={"session_id": sid}),
                  {"marks": [{"studentId": str(e["p1"].id), "status": "present"}]}, format="json")
    assert mark.status_code == 200
    # Re-opening the same day returns the same session (one per batch/day).
    resp2 = c.post(reverse("attendance:session-open"),
                   {"batchId": str(e["batch"].id), "date": datetime.date.today().isoformat()}, format="json")
    assert _data(resp2)["session"]["id"] == sid


def test_session_mode_requires_subject_and_slot():
    e = _build(attendance_mode="session")
    c = _client(e["faculty"])
    # Missing subject/slot in session mode → 400.
    resp = c.post(reverse("attendance:session-open"),
                  {"batchId": str(e["batch"].id), "date": datetime.date.today().isoformat()}, format="json")
    assert resp.status_code == 400


# ── Backend geo-fence validation ──────────────────────────────────────────────
def test_geofence_inside_radius_ok():
    # Branch at (12.9716, 77.5946), 200 m radius. Mark ~50 m away → allowed.
    e = _build(lat="12.971600", lng="77.594600", radius=200)
    c = _client(e["faculty"])
    resp = c.post(reverse("attendance:session-open"),
                  {"batchSubjectId": str(e["bs"].id), "date": datetime.date.today().isoformat(),
                   "periodSlotId": str(e["slot"].id)}, format="json")
    sid = _data(resp)["session"]["id"]
    c.post(reverse("attendance:session-mark", kwargs={"session_id": sid}),
           {"marks": [{"studentId": str(e["p1"].id), "status": "present",
                       "geoLat": "12.971900", "geoLng": "77.594600"}]}, format="json")
    rec = AttendanceRecord.objects.get(session_id=sid)
    assert rec.status == AttendanceStatus.PRESENT  # inside fence → not flagged


def test_geofence_outside_radius_flagged():
    # Same branch, but mark ~3 km away → backend flags it (no client geoValid needed).
    e = _build(lat="12.971600", lng="77.594600", radius=200)
    c = _client(e["faculty"])
    resp = c.post(reverse("attendance:session-open"),
                  {"batchSubjectId": str(e["bs"].id), "date": datetime.date.today().isoformat(),
                   "periodSlotId": str(e["slot"].id)}, format="json")
    sid = _data(resp)["session"]["id"]
    c.post(reverse("attendance:session-mark", kwargs={"session_id": sid}),
           {"marks": [{"studentId": str(e["p1"].id), "status": "present",
                       "geoLat": "13.000000", "geoLng": "77.594600"}]}, format="json")
    rec = AttendanceRecord.objects.get(session_id=sid)
    assert rec.status == AttendanceStatus.FLAGGED
    assert rec.audits.filter(audit_type="geo_fence_failure").exists()


def test_no_geofence_configured_never_flags():
    # Branch has no coordinates → geo is stored but never flagged.
    e = _build()  # no lat/lng/radius
    c = _client(e["faculty"])
    resp = c.post(reverse("attendance:session-open"),
                  {"batchSubjectId": str(e["bs"].id), "date": datetime.date.today().isoformat(),
                   "periodSlotId": str(e["slot"].id)}, format="json")
    sid = _data(resp)["session"]["id"]
    c.post(reverse("attendance:session-mark", kwargs={"session_id": sid}),
           {"marks": [{"studentId": str(e["p1"].id), "status": "present",
                       "geoLat": "50.0", "geoLng": "50.0"}]}, format="json")
    rec = AttendanceRecord.objects.get(session_id=sid)
    assert rec.status == AttendanceStatus.PRESENT
