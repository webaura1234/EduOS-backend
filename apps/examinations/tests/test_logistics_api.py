"""End-to-end tests for seating and invigilator logistics (Stage 4.3)."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import AcademicPeriod, AcademicYear, Batch, Course, Department, Room, Subject
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.examinations.models import InvigilatorDuty, Seating
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
def logistics_env():
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
    room_a = Room.objects.create(branch=branch, name="Hall A", capacity=40)
    room_small_a = Room.objects.create(branch=branch, name="Small A", capacity=3)
    room_small_b = Room.objects.create(branch=branch, name="Small B", capacity=3)
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=tenant,
        branch=branch,
        phone="+919800000020",
        custom_login_id=None,
        must_change_password=False,
    )
    faculty1 = UserFactory(
        role=Role.FACULTY,
        tenant=tenant,
        branch=branch,
        custom_login_id="FAC-1",
        must_change_password=False,
    )
    faculty2 = UserFactory(
        role=Role.FACULTY,
        tenant=tenant,
        branch=branch,
        custom_login_id="FAC-2",
        must_change_password=False,
    )
    students = []
    for i in range(5):
        user = UserFactory(
            role=Role.STUDENT,
            tenant=tenant,
            branch=branch,
            custom_login_id=f"STU-{i}",
            must_change_password=False,
        )
        _p = StudentProfile.objects.create(user=user, current_batch=batch, academic_status=AcademicStatus.ACTIVE)
        from apps.admissions.queries.enrollment import resolve_enrollment_for_profile
        resolve_enrollment_for_profile(_p)
        students.append(_p)
    return dict(
        tenant=tenant,
        branch=branch,
        period=period,
        batch=batch,
        subject=subject,
        room_a=room_a,
        room_small_a=room_small_a,
        room_small_b=room_small_b,
        admin=admin,
        faculty1=faculty1,
        faculty2=faculty2,
        students=students,
    )


def _setup_exam_with_slot(env, client):
    exam_resp = client.post(
        reverse("examinations:exam-list"),
        {
            "name": "Final Exam",
            "examType": "final",
            "academicPeriodId": str(env["period"].id),
            "examFeePaise": 0,
        },
        format="json",
    )
    exam_id = _data(exam_resp)["exam"]["id"]
    slot_resp = client.post(
        reverse("examinations:exam-schedule-list", kwargs={"exam_id": exam_id}),
        {
            "classSectionId": str(env["batch"].id),
            "subjectId": str(env["subject"].id),
            "date": "2024-09-15",
            "startTime": "09:00",
            "endTime": "11:00",
            "roomId": str(env["room_a"].id),
            "override": True,
        },
        format="json",
    )
    slot_id = _data(slot_resp)["slot"]["id"]
    client.post(
        reverse("examinations:exam-register", kwargs={"exam_id": exam_id}),
        {"classSectionId": str(env["batch"].id)},
        format="json",
    )
    return exam_id, slot_id


def test_seating_generate_single_room(logistics_env):
    client = _client(logistics_env["admin"])
    exam_id, slot_id = _setup_exam_with_slot(logistics_env, client)

    resp = client.post(
        reverse("examinations:exam-seating-generate", kwargs={"exam_id": exam_id}),
        {"examSlotId": slot_id},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    plan = _data(resp)["seatingPlans"][0]
    assert plan["totalStudents"] == 5
    assert Seating.objects.filter(schedule_slot_id=slot_id, is_active=True).count() == 5


def test_seating_partial_last_room(logistics_env):
    """EC-EXAM-05 — 5 students across two rooms (3 + 2 partial fill)."""
    client = _client(logistics_env["admin"])
    exam_id, slot_id = _setup_exam_with_slot(logistics_env, client)

    resp = client.post(
        reverse("examinations:exam-seating-generate", kwargs={"exam_id": exam_id}),
        {
            "examSlotId": slot_id,
            "roomIds": [str(logistics_env["room_small_a"].id), str(logistics_env["room_small_b"].id)],
        },
        format="json",
    )
    assert resp.status_code == 201, resp.content
    plan = _data(resp)["seatingPlans"][0]
    assert len(plan["allocations"]) == 2
    assert len(plan["allocations"][0]["seats"]) == 3
    assert len(plan["allocations"][1]["seats"]) == 2
    assert "EC-EXAM-05" in plan["note"]


def test_invigilator_auto_and_manual(logistics_env):
    client = _client(logistics_env["admin"])
    exam_id, slot_id = _setup_exam_with_slot(logistics_env, client)

    auto = client.post(
        reverse("examinations:exam-invigilators", kwargs={"exam_id": exam_id}),
        {"autoAssign": True},
        format="json",
    )
    assert auto.status_code == 201, auto.content
    assert len(_data(auto)["invigilation"]) == 1

    manual = client.post(
        reverse("examinations:exam-invigilators", kwargs={"exam_id": exam_id}),
        {"examSlotId": slot_id, "facultyId": str(logistics_env["faculty2"].id)},
        format="json",
    )
    assert manual.status_code == 201
    assert _data(manual)["invigilation"][0]["facultyId"] == str(logistics_env["faculty2"].id)
    assert InvigilatorDuty.objects.filter(schedule_slot_id=slot_id, is_active=True).count() == 1


def test_invigilator_conflict_blocked(logistics_env):
    client = _client(logistics_env["admin"])
    exam_id, slot_id = _setup_exam_with_slot(logistics_env, client)

    assert client.post(
        reverse("examinations:exam-invigilators", kwargs={"exam_id": exam_id}),
        {"examSlotId": slot_id, "facultyId": str(logistics_env["faculty1"].id)},
        format="json",
    ).status_code == 201

    batch_b = Batch.objects.create(
        course=logistics_env["batch"].course,
        academic_year=logistics_env["batch"].academic_year,
        name="B",
    )
    exam2_resp = client.post(
        reverse("examinations:exam-list"),
        {"name": "Other Exam", "examType": "unit", "academicPeriodId": str(logistics_env["period"].id)},
        format="json",
    )
    exam2_id = _data(exam2_resp)["exam"]["id"]
    slot2_resp = client.post(
        reverse("examinations:exam-schedule-list", kwargs={"exam_id": exam2_id}),
        {
            "classSectionId": str(batch_b.id),
            "subjectId": str(logistics_env["subject"].id),
            "date": "2024-09-15",
            "startTime": "09:30",
            "endTime": "11:30",
            "roomId": str(logistics_env["room_small_b"].id),
            "override": True,
        },
        format="json",
    )
    assert slot2_resp.status_code == 201, slot2_resp.content
    slot2_id = _data(slot2_resp)["slot"]["id"]

    conflict = client.post(
        reverse("examinations:exam-invigilators", kwargs={"exam_id": exam2_id}),
        {"examSlotId": slot2_id, "facultyId": str(logistics_env["faculty1"].id)},
        format="json",
    )
    assert conflict.status_code == 400
