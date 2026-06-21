"""Admin Academics gap-domain write actions + their reflection in the aggregate."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.academics.models import PeriodSlot, Timetable, TimetableEntry
from apps.academics.models.curriculum import BatchSubject, Subject
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
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch,
                        phone="+919810000001", custom_login_id=None,
                        must_change_password=False)
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                          custom_login_id="FAC-1", must_change_password=False)
    return dict(tenant=tenant, branch=branch, admin=admin, faculty=faculty)


def _timetable_entry(env):
    year = AcademicYearFactory(branch=env["branch"])
    batch = BatchFactory(course__department__branch=env["branch"], academic_year=year)
    subject = Subject.objects.create(course=batch.course, name="Maths", code="MA")
    from apps.academics.models.calendar import AcademicPeriod, PeriodType
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type=PeriodType.TERM, sequence=1, name="Term 1",
        start_date=datetime.date(2025, 6, 1), end_date=datetime.date(2025, 10, 1),
    )
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    slot = PeriodSlot.objects.create(
        branch=env["branch"], name="P1", sequence=1,
        start_time=datetime.time(9, 0), end_time=datetime.time(10, 0),
    )
    tt = Timetable.objects.create(batch=batch, academic_period=period)
    return TimetableEntry.objects.create(
        timetable=tt, batch_subject=bs, period_slot=slot, day_of_week=1,
        faculty=env["faculty"], status="active",
    )


def _post(env, body):
    return _client(env["admin"]).post(
        reverse("academics:admin-actions"), body, format="json",
    )


def _overview(env):
    return _data(_client(env["admin"]).get(reverse("academics:admin-overview")))


def test_set_working_days(env):
    rules = [{"dayOfWeek": d, "label": "", "isWorkingDay": d in (1, 2, 3, 4, 5)}
             for d in range(7)]
    resp = _post(env, {"action": "set_working_days", "rules": rules})
    assert resp.status_code == 200, resp.content

    wd = {d["dayOfWeek"]: d["isWorkingDay"] for d in _overview(env)["workingDays"]}
    assert wd[6] is False  # Saturday now off
    assert wd[1] is True


def test_create_and_cancel_substitution(env):
    entry = _timetable_entry(env)
    resp = _post(env, {"action": "create_substitution", "payload": {
        "timetableSlotId": str(entry.id),
        "substituteFacultyUserId": str(env["faculty"].id),
        "date": "2026-06-22", "reason": "On leave",
    }})
    assert resp.status_code == 201, resp.content
    sub_id = _data(resp)["id"]

    subs = _overview(env)["substitutions"]
    assert any(s["id"] == sub_id for s in subs)

    resp = _post(env, {"action": "cancel_substitution", "substitutionId": sub_id})
    assert resp.status_code == 200
    assert _data(resp)["status"] == "cancelled"


def test_upload_and_delete_study_material(env):
    entry = _timetable_entry(env)
    resp = _post(env, {"action": "upload_study_material", "payload": {
        "timetableSlotId": str(entry.id), "sessionDate": "2026-06-22",
        "fileName": "notes.pdf", "s3Key": "materials/notes.pdf",
    }})
    assert resp.status_code == 201, resp.content
    mid = _data(resp)["id"]
    assert any(m["id"] == mid for m in _overview(env)["studyMaterials"])

    resp = _post(env, {"action": "delete_study_material", "materialId": mid})
    assert resp.status_code == 200
    assert all(m["id"] != mid for m in _overview(env)["studyMaterials"])


def test_save_period_derives_type_and_sequence(env):
    year = AcademicYearFactory(branch=env["branch"], is_current=True)
    resp = _post(env, {"action": "save_period", "payload": {
        "label": "Term 1", "startDate": "2025-06-01", "endDate": "2025-10-01",
        "academicYearId": str(year.id),
    }})
    assert resp.status_code == 201, resp.content
    periods = _overview(env)["periods"]
    assert any(p["label"] == "Term 1" and p["kind"] == "term" for p in periods)


def test_save_department_and_hierarchy(env):
    resp = _post(env, {"action": "save_department", "payload": {"name": "Science"}})
    assert resp.status_code == 201, resp.content
    parent_id = _data(resp)["id"]

    resp = _post(env, {"action": "save_department",
                       "payload": {"name": "Physics", "parentId": parent_id}})
    assert resp.status_code == 201, resp.content
    child_id = _data(resp)["id"]

    depts = {d["id"]: d for d in _overview(env)["departments"]}
    assert depts[child_id]["parentId"] == parent_id
    assert depts[parent_id]["parentId"] is None


def test_save_subject_resolves_default_course(env):
    resp = _post(env, {"action": "save_subject",
                       "payload": {"name": "Mathematics", "code": "MATH", "credits": 4}})
    assert resp.status_code == 201, resp.content
    subjects = _overview(env)["subjects"]
    assert any(s["name"] == "Mathematics" and s["code"] == "MATH" for s in subjects)


def test_save_class_section_requires_current_year(env):
    # No current year yet → clear error.
    resp = _post(env, {"action": "save_class_section", "payload": {"label": "10-A"}})
    assert resp.status_code == 400

    AcademicYearFactory(branch=env["branch"], is_current=True)
    resp = _post(env, {"action": "save_class_section", "payload": {"label": "10-A"}})
    assert resp.status_code == 201, resp.content
    sections = _overview(env)["classSections"]
    assert any(s["label"] == "10-A" for s in sections)


def test_save_timetable_slot_creates_entry(env):
    from apps.academics.models.calendar import AcademicPeriod, PeriodType
    year = AcademicYearFactory(branch=env["branch"], is_current=True)
    AcademicPeriod.objects.create(
        academic_year=year, period_type=PeriodType.TERM, sequence=1, name="Term 1",
        start_date=datetime.date(2025, 6, 1), end_date=datetime.date(2025, 10, 1),
    )
    batch = BatchFactory(course__department__branch=env["branch"], academic_year=year)
    subject = Subject.objects.create(course=batch.course, name="Maths", code="MA")

    resp = _post(env, {"action": "save_timetable_slot", "payload": {
        "classSectionId": str(batch.id), "subjectId": str(subject.id),
        "facultyUserId": str(env["faculty"].id), "roomId": "",
        "dayOfWeek": 1, "periodIndex": 1, "startTime": "09:00", "endTime": "10:00",
    }})
    assert resp.status_code == 201, resp.content
    slots = _overview(env)["timetableSlots"]
    assert any(s["classSectionId"] == str(batch.id) and s["subjectId"] == str(subject.id)
               for s in slots)


def test_save_timetable_slot_requires_period(env):
    batch = BatchFactory(course__department__branch=env["branch"])
    subject = Subject.objects.create(course=batch.course, name="Sci", code="SC")
    resp = _post(env, {"action": "save_timetable_slot", "payload": {
        "classSectionId": str(batch.id), "subjectId": str(subject.id),
        "facultyUserId": "__unassigned__", "dayOfWeek": 2, "periodIndex": 1,
    }})
    assert resp.status_code == 400  # no current year/period set


def test_review_queue_flags_unassigned_faculty(env):
    entry = _timetable_entry(env)
    entry.faculty = None
    entry.save(update_fields=["faculty"])
    queue = _overview(env)["adminReviewQueue"]
    assert any(item["type"] == "faculty_unassigned" for item in queue)
