"""End-to-end validation of the academics API (Stage 1)."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _data(resp):
    body = resp.json()
    return body.get("data", body)


@pytest.fixture
def tenant():
    return TenantFactory(institution_type="school")


@pytest.fixture
def branch(tenant):
    return BranchFactory(tenant=tenant)


@pytest.fixture
def admin(tenant, branch):
    return UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch,
                       phone="+919900001111", custom_login_id=None, must_change_password=False)


@pytest.fixture
def faculty(tenant, branch):
    return UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                       custom_login_id="FAC-T1", must_change_password=False)


@pytest.fixture
def client(admin):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(admin)}")
    return c


def _create(client, name, payload, key):
    resp = client.post(reverse(f"academics:{name}"), payload, format="json")
    assert resp.status_code == 201, resp.content
    return _data(resp)[key]


def test_calendar_lifecycle(client):
    year = _create(client, "academic-years",
                   {"name": "2024-25", "startDate": "2024-06-01", "endDate": "2025-04-30", "isCurrent": True},
                   "academicYear")
    assert year["isCurrent"] is True

    # second current year via action → first must flip off
    year2 = _create(client, "academic-years",
                    {"name": "2025-26", "startDate": "2025-06-01", "endDate": "2026-04-30"},
                    "academicYear")
    resp = client.patch(reverse("academics:academic-year-actions"),
                        {"action": "set_current", "yearId": year2["id"]}, format="json")
    assert resp.status_code == 200
    assert _data(resp)["academicYear"]["isCurrent"] is True

    listing = _data(client.get(reverse("academics:academic-years")))["academicYears"]
    current = [y for y in listing if y["isCurrent"]]
    assert len(current) == 1 and current[0]["id"] == year2["id"]


def test_end_date_validation(client):
    resp = client.post(reverse("academics:academic-years"),
                       {"name": "Bad", "startDate": "2025-04-30", "endDate": "2024-06-01"}, format="json")
    assert resp.status_code == 400


def _build_structure(client):
    """Create year→period and department→course→batch→subjects; return ids."""
    year = _create(client, "academic-years",
                   {"name": "2024-25", "startDate": "2024-06-01", "endDate": "2025-04-30", "isCurrent": True},
                   "academicYear")
    period = client.post(reverse("academics:academic-periods", kwargs={"year_id": year["id"]}),
                         {"periodType": "term", "sequence": 1, "name": "Term 1",
                          "startDate": "2024-06-01", "endDate": "2024-10-31"}, format="json")
    period = _data(period)["period"]
    dept = _create(client, "departments", {"name": "Science", "departmentType": "stream"}, "department")
    course = _create(client, "courses", {"departmentId": dept["id"], "name": "Grade 9"}, "course")
    batch = _create(client, "batches",
                    {"courseId": course["id"], "academicYearId": year["id"], "name": "Section A"}, "batch")
    s1 = _create(client, "subjects", {"courseId": course["id"], "name": "Maths", "code": "MTH9"}, "subject")
    s2 = _create(client, "subjects", {"courseId": course["id"], "name": "Physics", "code": "PHY9"}, "subject")
    return {"year": year, "period": period, "course": course, "batch": batch, "s1": s1, "s2": s2}


def test_structure_chain(client):
    ids = _build_structure(client)
    assert ids["batch"]["courseId"] == ids["course"]["id"]
    # duplicate department name rejected
    _create(client, "departments", {"name": "Commerce", "departmentType": "stream"}, "department")
    dup = client.post(reverse("academics:departments"),
                     {"name": "Commerce", "departmentType": "stream"}, format="json")
    assert dup.status_code == 400


def test_timetable_clash_detection(client, faculty):
    ids = _build_structure(client)
    bs1 = _create(client, "batch-subjects",
                  {"batchId": ids["batch"]["id"], "subjectId": ids["s1"]["id"],
                   "academicPeriodId": ids["period"]["id"]}, "batchSubject")
    bs2 = _create(client, "batch-subjects",
                  {"batchId": ids["batch"]["id"], "subjectId": ids["s2"]["id"],
                   "academicPeriodId": ids["period"]["id"]}, "batchSubject")
    slot = _create(client, "period-slots",
                   {"name": "Period 1", "sequence": 1, "startTime": "09:00", "endTime": "09:45"}, "periodSlot")

    # NEW endpoint: create the timetable container
    tt = _create(client, "timetables",
                 {"batchId": ids["batch"]["id"], "academicPeriodId": ids["period"]["id"]}, "timetable")

    entries_url = reverse("academics:timetable-entries", kwargs={"timetable_id": tt["id"]})
    e1 = client.post(entries_url,
                     {"batchSubjectId": bs1["id"], "periodSlotId": slot["id"],
                      "dayOfWeek": 1, "facultyId": str(faculty.id)}, format="json")
    assert e1.status_code == 201, e1.content

    # Same faculty, same slot, same day → clash 400
    clash = client.post(entries_url,
                        {"batchSubjectId": bs2["id"], "periodSlotId": slot["id"],
                         "dayOfWeek": 1, "facultyId": str(faculty.id)}, format="json")
    assert clash.status_code == 400
    assert "clash" in clash.content.decode().lower()

    # Different day → no clash
    ok = client.post(entries_url,
                     {"batchSubjectId": bs2["id"], "periodSlotId": slot["id"],
                      "dayOfWeek": 2, "facultyId": str(faculty.id)}, format="json")
    assert ok.status_code == 201, ok.content


def test_holiday_create(client):
    h = _create(client, "holidays",
                {"date": "2024-08-15", "name": "Independence Day", "holidayType": "public"}, "holiday")
    assert h["name"] == "Independence Day"


def test_permission_denied_for_student(tenant, branch):
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                          custom_login_id="STU-X", must_change_password=False)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(student)}")
    assert c.get(reverse("academics:academic-years")).status_code == 403
