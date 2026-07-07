"""Admin Examinations overview — the batched aggregate that replaced an N+1
Next.js BFF loop (schedule/students/results/invigilators/seating fetched once
per exam, students once per class-section per exam)."""

import datetime

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import AcademicPeriod, AcademicYear, Batch, Course, Department, Room, Subject
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.queries.enrollment import resolve_enrollment_for_profile
from apps.examinations.models import Exam, ResultPublication
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
    current_year = AcademicYear.objects.create(
        branch=branch, name="2026-27", is_current=True,
        start_date=datetime.date(2026, 6, 1), end_date=datetime.date(2027, 4, 30),
    )
    current_period = AcademicPeriod.objects.create(
        academic_year=current_year, period_type="term", sequence=1, name="Term 1",
        start_date=datetime.date(2026, 6, 1), end_date=datetime.date(2026, 10, 31),
    )
    old_year = AcademicYear.objects.create(
        branch=branch, name="2020-21", is_current=False,
        start_date=datetime.date(2020, 6, 1), end_date=datetime.date(2021, 4, 30),
    )
    old_period = AcademicPeriod.objects.create(
        academic_year=old_year, period_type="term", sequence=1, name="Term 1",
        start_date=datetime.date(2020, 6, 1), end_date=datetime.date(2020, 10, 31),
    )
    dept = Department.objects.create(branch=branch, name="Science", department_type="stream")
    course = Course.objects.create(department=dept, name="Grade 9")
    batch = Batch.objects.create(course=course, academic_year=current_year, name="A")
    subject = Subject.objects.create(course=course, name="Maths", code="MTH9", max_marks=100)
    room = Room.objects.create(branch=branch, name="Hall A", capacity=40)
    admin = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch,
        phone="+919800000030", custom_login_id=None, must_change_password=False,
    )
    faculty = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-AO-1", must_change_password=False,
    )
    return dict(
        tenant=tenant, branch=branch, current_period=current_period, old_period=old_period,
        course=course, batch=batch, subject=subject, room=room, admin=admin, faculty=faculty,
    )


def _make_student(env, tag):
    user = UserFactory(
        role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
        custom_login_id=f"STU-AO-{tag}", must_change_password=False,
    )
    profile = StudentProfile.objects.create(
        user=user, current_batch=env["batch"], academic_status=AcademicStatus.ACTIVE,
    )
    return resolve_enrollment_for_profile(profile)


def _setup_exam_with_slot(env, client, *, period, name, offset=0):
    exam_resp = client.post(
        reverse("examinations:exam-list"),
        {"name": name, "examType": "final", "academicPeriodId": str(period.id), "examFeePaise": 0},
        format="json",
    )
    assert exam_resp.status_code == 201, exam_resp.content
    exam_id = _data(exam_resp)["exam"]["id"]
    slot_resp = client.post(
        reverse("examinations:exam-schedule-list", kwargs={"exam_id": exam_id}),
        {
            "classSectionId": str(env["batch"].id), "subjectId": str(env["subject"].id),
            "date": f"2026-09-{15 + offset}", "startTime": "09:00", "endTime": "11:00",
            "roomId": str(env["room"].id), "override": True,
        },
        format="json",
    )
    assert slot_resp.status_code == 201, slot_resp.content
    slot_id = _data(slot_resp)["slot"]["id"]
    reg_resp = client.post(
        reverse("examinations:exam-register", kwargs={"exam_id": exam_id}),
        {"classSectionId": str(env["batch"].id)},
        format="json",
    )
    assert reg_resp.status_code == 201, reg_resp.content
    return exam_id, slot_id


def test_admin_overview_scopes_to_current_year_and_batches_everything(env):
    client = _client(env["admin"])
    _make_student(env, "1")

    old_exam_id, _ = _setup_exam_with_slot(env, client, period=env["old_period"], name="Old Final", offset=0)
    exam_id, slot_id = _setup_exam_with_slot(
        env, client, period=env["current_period"], name="Current Final", offset=1,
    )

    inv_resp = client.post(
        reverse("examinations:exam-invigilators", kwargs={"exam_id": exam_id}),
        {"autoAssign": True}, format="json",
    )
    assert inv_resp.status_code == 201, inv_resp.content

    seat_resp = client.post(
        reverse("examinations:exam-seating-generate", kwargs={"exam_id": exam_id}),
        {"examSlotId": slot_id}, format="json",
    )
    assert seat_resp.status_code == 201, seat_resp.content

    ResultPublication.objects.create(
        exam_id=exam_id, published_at=datetime.datetime.now(datetime.timezone.utc),
        snapshot_hash="abc123", revision_no=1, is_current=True,
    )
    # Mirror what the real publish interactor sets on Exam (is_published/
    # result_status are denormalized there, not derived from ResultPublication).
    Exam.objects.filter(pk=exam_id).update(is_published=True, result_status="published")

    resp = client.get(reverse("examinations:admin-overview"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)

    exam_ids_in_response = {e["id"] for e in body["exams"]}
    assert exam_id in exam_ids_in_response
    assert old_exam_id not in exam_ids_in_response

    assert any(s["id"] == slot_id for s in body["slots"])
    assert len(body["students"]) == 1
    assert body["students"][0]["classLabel"] == "A"

    assert len(body["seatingPlans"]) == 1
    assert body["seatingPlans"][0]["examSlotId"] == slot_id
    assert body["seatingPlans"][0]["totalStudents"] == 1

    assert len(body["invigilation"]) == 1
    assert body["invigilation"][0]["examSlotId"] == slot_id

    assert body["resultStatusByExam"][slot_id] == "published"
    assert len(body["publishedResults"]) == 1
    assert body["publishedResults"][0]["examSlotId"] == slot_id
    assert body["publishedResults"][0]["revisionNo"] == 1


def test_admin_overview_query_count_does_not_scale_with_exam_count(env):
    """Baseline must be a single exam, not zero: Django's ``field__in=[]``
    optimization skips a batched query's SQL entirely when there's nothing to
    fetch, so a zero-exam baseline would make the fixed batched-query cost look
    like per-exam growth instead of the one-time cost it actually is."""
    client = _client(env["admin"])
    for i in range(5):
        _make_student(env, f"bulk{i}")

    _setup_exam_with_slot(env, client, period=env["current_period"], name="Exam A", offset=0)
    with CaptureQueriesContext(connection) as ctx_one:
        resp = client.get(reverse("examinations:admin-overview"))
    assert resp.status_code == 200, resp.content
    assert len(_data(resp)["exams"]) == 1
    queries_one_exam = len(ctx_one.captured_queries)

    for i, name in enumerate(["Exam B", "Exam C", "Exam D"], start=1):
        _setup_exam_with_slot(env, client, period=env["current_period"], name=name, offset=i)

    with CaptureQueriesContext(connection) as ctx_many:
        resp2 = client.get(reverse("examinations:admin-overview"))
    assert resp2.status_code == 200, resp2.content
    queries_many_exams = len(ctx_many.captured_queries)

    assert len(_data(resp2)["exams"]) == 4
    assert queries_many_exams <= queries_one_exam + 2, (
        f"admin-overview query count scales with exam count: {queries_one_exam} -> {queries_many_exams}"
    )


def test_admin_overview_requires_admin(env):
    student_user = UserFactory(
        role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
        custom_login_id="STU-AO-NOADMIN", must_change_password=False,
    )
    resp = _client(student_user).get(reverse("examinations:admin-overview"))
    assert resp.status_code == 403
