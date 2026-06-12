"""End-to-end tests for examinations setup API (Stage 4.1)."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import (
    AcademicPeriod,
    AcademicYear,
    Batch,
    Course,
    Department,
    Holiday,
    Room,
    Subject,
)
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
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
    room_b = Room.objects.create(branch=branch, name="Hall B", capacity=40)
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919800000001",
        custom_login_id=None,
        must_change_password=False,
    )
    return dict(
        tenant=tenant,
        branch=branch,
        year=year,
        period=period,
        course=course,
        batch=batch,
        subject=subject,
        room=room,
        room_b=room_b,
        admin=admin,
    )


def _create_exam(env, client):
    resp = client.post(
        reverse("examinations:exam-list"),
        {
            "name": "Mid-Term",
            "examType": "midterm",
            "academicPeriodId": str(env["period"].id),
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    return _data(resp)["exam"]["id"]


def _slot_payload(env, **overrides):
    payload = {
        "name": "Maths Mid-Term",
        "classSectionId": str(env["batch"].id),
        "subjectId": str(env["subject"].id),
        "date": "2024-09-15",
        "startTime": "09:00",
        "endTime": "11:00",
        "roomId": str(env["room"].id),
        "status": "draft",
    }
    payload.update(overrides)
    return payload


def test_exam_and_schedule_happy_path(env):
    client = _client(env["admin"])
    exam_id = _create_exam(env, client)

    resp = client.post(
        reverse("examinations:exam-schedule-list", kwargs={"exam_id": exam_id}),
        _slot_payload(env),
        format="json",
    )
    assert resp.status_code == 201, resp.content
    slot = _data(resp)["slot"]
    assert slot["subjectName"] == "Maths"
    assert slot["roomName"] == "Hall A"
    assert slot["date"] == "2024-09-15"

    list_resp = client.get(reverse("examinations:exam-schedule-list", kwargs={"exam_id": exam_id}))
    assert list_resp.status_code == 200
    assert len(_data(list_resp)["slots"]) == 1


def test_grade_scale_crud(env):
    client = _client(env["admin"])
    resp = client.post(
        reverse("examinations:grade-scale-list"),
        {
            "courseId": str(env["course"].id),
            "name": "Standard",
            "bands": [{"minPercent": 60, "maxPercent": 100, "grade": "A", "gradePoint": 9}],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    scale_id = _data(resp)["gradeScale"]["id"]

    patch = client.patch(
        reverse("examinations:grade-scale-detail", kwargs={"scale_id": scale_id}),
        {"name": "Updated", "version": 1},
        format="json",
    )
    assert patch.status_code == 200
    assert _data(patch)["gradeScale"]["name"] == "Updated"


def test_room_clash_blocked(env):
    """EC-EXAM-06 — overlapping room booking returns 400."""
    client = _client(env["admin"])
    exam_id = _create_exam(env, client)
    url = reverse("examinations:exam-schedule-list", kwargs={"exam_id": exam_id})

    assert client.post(url, _slot_payload(env), format="json").status_code == 201
    clash = client.post(
        url,
        _slot_payload(env, startTime="09:30", endTime="10:30"),
        format="json",
    )
    assert clash.status_code == 400
    body = clash.json()
    assert "clashes" in body.get("errors", {})


def test_holiday_warning_requires_override(env):
    """EC-TT-03 — exam on holiday returns 200 with requiresOverride unless override=true."""
    Holiday.objects.create(
        branch=env["branch"],
        date=datetime.date(2024, 9, 15),
        name="Festival",
        holiday_type="public",
        applies_to={"all": True},
    )
    client = _client(env["admin"])
    exam_id = _create_exam(env, client)
    url = reverse("examinations:exam-schedule-list", kwargs={"exam_id": exam_id})

    warn = client.post(url, _slot_payload(env), format="json")
    assert warn.status_code == 200
    body = _data(warn)
    assert body["requiresOverride"] is True
    assert body["warnings"][0]["type"] == "holiday"

    created = client.post(url, _slot_payload(env, override=True), format="json")
    assert created.status_code == 201
