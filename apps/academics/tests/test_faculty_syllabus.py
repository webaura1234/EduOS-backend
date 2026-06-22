"""Faculty syllabus tracking — subjects with units + completion percent + update."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import SyllabusUnit
from apps.academics.models.calendar import AcademicPeriod, PeriodType
from apps.academics.models.curriculum import BatchFaculty, BatchSubject, Subject
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
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
    year = AcademicYearFactory(branch=branch, is_current=True)
    batch = BatchFactory(course__department__branch=branch, academic_year=year)
    subject = Subject.objects.create(course=batch.course, name="Maths", code="MA")
    period = AcademicPeriod.objects.create(
        academic_year=year, period_type=PeriodType.TERM, sequence=1, name="T1",
        start_date=datetime.date(2026, 1, 1), end_date=datetime.date(2026, 12, 1))
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch,
                          custom_login_id="FAC-1", must_change_password=False)
    BatchFaculty.objects.create(batch_subject=bs, faculty=faculty, role="primary",
                                assigned_at=datetime.date(2026, 1, 1))
    u1 = SyllabusUnit.objects.create(branch=branch, subject=subject, title="Algebra", order=1)
    u2 = SyllabusUnit.objects.create(branch=branch, subject=subject, title="Geometry", order=2)
    return dict(branch=branch, faculty=faculty, subject=subject, batch=batch, u1=u1, u2=u2)


def test_lists_subject_with_units(env):
    body = _data(_client(env["faculty"]).get(reverse("academics:faculty-syllabus")))
    assert len(body["subjects"]) == 1
    s = body["subjects"][0]
    assert s["name"] == "Maths" and s["code"] == "MA"
    assert env["batch"].name in s["classLabels"]
    assert [u["title"] for u in s["syllabusUnits"]] == ["Algebra", "Geometry"]
    assert s["completedUnitIds"] == [] and s["syllabusCompletionPercent"] == 0


def test_update_completion(env):
    url = reverse("academics:faculty-syllabus")
    resp = _client(env["faculty"]).patch(url, {
        "subjectId": str(env["subject"].id),
        "completedUnitIds": [str(env["u1"].id)],
    }, format="json")
    assert resp.status_code == 200, resp.content
    s = _data(resp)["subject"]
    assert s["completedUnitIds"] == [str(env["u1"].id)]
    assert s["syllabusCompletionPercent"] == 50

    env["u1"].refresh_from_db()
    assert env["u1"].is_completed and env["u1"].completed_at is not None


def test_author_unit_crud(env):
    list_url = reverse("academics:syllabus-units")
    fc = _client(env["faculty"])

    # Create (order auto-assigned after the two seeded units).
    created = _data(fc.post(list_url, {
        "subjectId": str(env["subject"].id), "title": "Trigonometry",
    }, format="json"))["unit"]
    assert created["title"] == "Trigonometry" and created["order"] == 3

    # List for the subject.
    units = _data(fc.get(list_url, {"subjectId": str(env["subject"].id)}))["units"]
    assert len(units) == 3

    # Update.
    detail = reverse("academics:syllabus-unit-detail", args=[created["id"]])
    edited = _data(fc.patch(detail, {"title": "Trig", "order": 5}, format="json"))["unit"]
    assert edited["title"] == "Trig" and edited["order"] == 5

    # Delete (soft).
    assert fc.delete(detail).status_code == 200
    units = _data(fc.get(list_url, {"subjectId": str(env["subject"].id)}))["units"]
    assert len(units) == 2
