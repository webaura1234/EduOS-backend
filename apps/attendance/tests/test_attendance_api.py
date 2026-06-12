"""End-to-end tests for the attendance module — all EC-ATT edge cases."""

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
from apps.attendance.enums import AttendanceStatus, SessionStatus
from apps.attendance.models import AttendanceRecord, AttendanceSession
from apps.admissions.models import StudentEnrollment
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
    slot = PeriodSlot.objects.create(branch=branch, name="Period 1", sequence=1,
                                     start_time=datetime.time(9, 0), end_time=datetime.time(9, 45))
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919800000001",
                        custom_login_id=None, must_change_password=False)
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch, custom_login_id="FAC-1",
                          must_change_password=False)
    s1 = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-1",
                     must_change_password=False)
    s2 = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-2",
                     must_change_password=False)
    p1 = StudentProfile.objects.create(user=s1, current_batch=batch, academic_status=AcademicStatus.ACTIVE)
    p2 = StudentProfile.objects.create(user=s2, current_batch=batch, academic_status=AcademicStatus.ACTIVE)
    # Enrollment seam (Stage 5): attendance keys off StudentEnrollment.
    e1 = StudentEnrollment.objects.create(branch=branch, student_profile=p1, batch=batch, academic_year=year)
    e2 = StudentEnrollment.objects.create(branch=branch, student_profile=p2, batch=batch, academic_year=year)
    return dict(tenant=tenant, branch=branch, year=year, period=period, batch=batch, bs=bs,
                slot=slot, admin=admin, faculty=faculty, p1=p1, p2=p2, e1=e1, e2=e2)


def _open_session(env, date=None):
    c = _client(env["faculty"])
    resp = c.post(reverse("attendance:session-open"), {
        "batchSubjectId": str(env["bs"].id), "date": (date or datetime.date.today()).isoformat(),
        "periodSlotId": str(env["slot"].id),
    }, format="json")
    assert resp.status_code == 201, resp.content
    return _data(resp)["session"]["id"], c


# ── Happy path + EC-ATT-06 idempotent sync ────────────────────────────────────
def test_mark_and_idempotent_resync(env):
    sid, c = _open_session(env)
    url = reverse("attendance:session-mark", kwargs={"session_id": sid})
    payload = {"marks": [
        {"studentId": str(env["p1"].id), "status": "present"},
        {"studentId": str(env["p2"].id), "status": "absent"},
    ]}
    assert c.post(url, payload, format="json").status_code == 200
    assert AttendanceRecord.objects.filter(session_id=sid).count() == 2
    # Re-sync identical payload → still 2 records (EC-ATT-06)
    assert c.post(url, payload, format="json").status_code == 200
    assert AttendanceRecord.objects.filter(session_id=sid).count() == 2


# ── EC-ATT-01 holiday block ───────────────────────────────────────────────────
def test_mark_on_holiday_blocked(env):
    from apps.academics.models import Holiday
    today = datetime.date.today()
    Holiday.objects.create(branch=env["branch"], date=today, name="Festival",
                           holiday_type="public", applies_to={"all": True})
    sid, c = _open_session(env, today)
    resp = c.post(reverse("attendance:session-mark", kwargs={"session_id": sid}),
                  {"marks": [{"studentId": str(env["p1"].id), "status": "present"}]}, format="json")
    assert resp.status_code == 400
    assert "holiday" in resp.content.decode().lower()


# ── EC-ATT-02 late mark audit ─────────────────────────────────────────────────
def test_late_mark_audited(env, monkeypatch):
    sid, c = _open_session(env)
    # Force "now" to be well after the slot end + 2h grace.
    late_now = datetime.datetime.combine(datetime.date.today(), datetime.time(23, 0))
    monkeypatch.setattr("apps.attendance.interactors.marking.timezone.now", lambda: late_now)
    c.post(reverse("attendance:session-mark", kwargs={"session_id": sid}),
           {"marks": [{"studentId": str(env["p1"].id), "status": "present"}]}, format="json")
    rec = AttendanceRecord.objects.get(session_id=sid, student=env["e1"])
    assert rec.late_mark is True
    assert rec.audits.filter(audit_type="late_marking").exists()


# ── EC-ATT-03 geo-fence failure → flagged + queue ─────────────────────────────
def test_geo_fence_flagged(env):
    sid, c = _open_session(env)
    c.post(reverse("attendance:session-mark", kwargs={"session_id": sid}),
           {"marks": [{"studentId": str(env["p1"].id), "status": "present",
                       "geoLat": "1.0", "geoLng": "1.0", "geoValid": False}]}, format="json")
    rec = AttendanceRecord.objects.get(session_id=sid, student=env["e1"])
    assert rec.status == AttendanceStatus.FLAGGED
    assert rec.audits.filter(audit_type="geo_fence_failure").exists()
    flagged = _data(_client(env["admin"]).get(reverse("attendance:flagged")))["flagged"]
    assert any(f["recordId"] == str(rec.id) for f in flagged)


# ── EC-ATT-04 retroactive correction with audit diff ─────────────────────────
def test_retroactive_correction(env):
    sid, c = _open_session(env)
    c.post(reverse("attendance:session-mark", kwargs={"session_id": sid}),
           {"marks": [{"studentId": str(env["p1"].id), "status": "present"}]}, format="json")
    rec = AttendanceRecord.objects.get(session_id=sid, student=env["e1"])
    resp = _client(env["admin"]).patch(
        reverse("attendance:record-correct", kwargs={"record_id": str(rec.id)}),
        {"newStatus": "absent", "reason": "Marked wrong"}, format="json")
    assert resp.status_code == 200
    rec.refresh_from_db()
    assert rec.status == "absent"
    audit = rec.audits.get(audit_type="retroactive_edit")
    assert audit.original_status == "present" and audit.new_status == "absent"


# ── EC-ATT-05 exam-day excluded from % ────────────────────────────────────────
def test_exam_day_excluded_from_percent(env):
    env["tenant"].tenant_settings.exam_day_counts_toward_attendance = False
    env["tenant"].tenant_settings.save()
    # 1 normal session (absent) + 1 exam-day session (absent). Exam day must be excluded.
    normal = AttendanceSession.objects.create(branch=env["branch"], batch=env["batch"], batch_subject=env["bs"],
                                              period_slot=env["slot"], date=datetime.date(2024, 7, 1),
                                              status=SessionStatus.COMPLETED, is_exam_day=False)
    exam = AttendanceSession.objects.create(branch=env["branch"], batch=env["batch"], batch_subject=env["bs"],
                                            period_slot=env["slot"], date=datetime.date(2024, 7, 2),
                                            status=SessionStatus.COMPLETED, is_exam_day=True)
    for sess in (normal, exam):
        AttendanceRecord.objects.create(session=sess, student=env["e1"], status="absent",
                                        marked_at=datetime.datetime.now(),
                                        idempotency_key=f"{sess.id}:{env['p1'].id}")
    summary = _data(_client(env["p1"].user).get(reverse("attendance:student-summary")))
    # Only the 1 non-exam session counts → 0% over 1 session (not 2).
    assert summary["totalSessions"] == 1
    assert summary["overallPercent"] == 0.0


# ── Leave workflow + approved-leave converts absence ──────────────────────────
def test_leave_apply_approve_converts_absence(env):
    # Student is absent on a date.
    sess = AttendanceSession.objects.create(branch=env["branch"], batch=env["batch"], batch_subject=env["bs"],
                                            period_slot=env["slot"], date=datetime.date(2024, 7, 10),
                                            status=SessionStatus.COMPLETED)
    AttendanceRecord.objects.create(session=sess, student=env["e1"], status="absent",
                                    marked_at=datetime.datetime.now(),
                                    idempotency_key=f"{sess.id}:{env['p1'].id}")
    # Student applies for leave covering that date.
    apply = _client(env["p1"].user).post(reverse("attendance:leave"), {
        "studentId": str(env["p1"].id), "fromDate": "2024-07-10", "toDate": "2024-07-10",
        "reason": "Sick"}, format="json")
    assert apply.status_code == 201
    leave_id = _data(apply)["leave"]["id"]
    # Admin approves.
    review = _client(env["admin"]).patch(
        reverse("attendance:leave-review", kwargs={"leave_id": leave_id}),
        {"action": "approve"}, format="json")
    assert review.status_code == 200
    AttendanceRecord.objects.get(session=sess, student=env["e1"]).refresh_from_db()
    assert AttendanceRecord.objects.get(session=sess, student=env["e1"]).status == "leave"


# ── Shortage report respects threshold (F-105) ────────────────────────────────
def test_shortage_report(env):
    # 4 completed sessions; p1 present 1/4 = 25% (< 75) → shortage; p2 present 4/4 → not.
    for i in range(4):
        sess = AttendanceSession.objects.create(branch=env["branch"], batch=env["batch"], batch_subject=env["bs"],
                                                period_slot=env["slot"], date=datetime.date(2024, 7, i + 1),
                                                status=SessionStatus.COMPLETED)
        AttendanceRecord.objects.create(session=sess, student=env["e1"],
                                        status="present" if i == 0 else "absent",
                                        marked_at=datetime.datetime.now(),
                                        idempotency_key=f"{sess.id}:{env['p1'].id}")
        AttendanceRecord.objects.create(session=sess, student=env["e2"], status="present",
                                        marked_at=datetime.datetime.now(),
                                        idempotency_key=f"{sess.id}:{env['p2'].id}")
    rows = _data(_client(env["admin"]).get(reverse("attendance:report-shortage")))["rows"]
    ids = [r["studentId"] for r in rows]
    assert str(env["p1"].id) in ids and str(env["p2"].id) not in ids


# ── Frozen-year guard ─────────────────────────────────────────────────────────
def test_frozen_year_blocks_marking(env):
    sid, c = _open_session(env)
    env["year"].is_frozen = True
    env["year"].save(update_fields=["is_frozen"])
    resp = c.post(reverse("attendance:session-mark", kwargs={"session_id": sid}),
                  {"marks": [{"studentId": str(env["p1"].id), "status": "present"}]}, format="json")
    assert resp.status_code == 400


# ── Permissions ───────────────────────────────────────────────────────────────
def test_student_cannot_mark(env):
    sid, _ = _open_session(env)
    resp = _client(env["p1"].user).post(
        reverse("attendance:session-mark", kwargs={"session_id": sid}),
        {"marks": [{"studentId": str(env["p1"].id), "status": "present"}]}, format="json")
    assert resp.status_code == 403
