"""Faculty teaching assignments — my class vs other classes scoping."""

import datetime

import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.academics.models.calendar import AcademicPeriod, PeriodType
from apps.academics.models.curriculum import BatchFaculty, BatchSubject, Subject
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.examinations.models import Assignment
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db

URL = "examinations:faculty-teaching-assignments"


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def _due_at_future():
    return (timezone.now() + datetime.timedelta(days=7)).isoformat()


def _assign_subject_teacher(batch, faculty):
    subject = Subject.objects.create(course=batch.course, name="Maths", code="MA")
    period = AcademicPeriod.objects.create(
        academic_year=batch.academic_year,
        period_type=PeriodType.TERM,
        sequence=1,
        name="T1",
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 12, 1),
    )
    bs = BatchSubject.objects.create(batch=batch, subject=subject, academic_period=period)
    BatchFaculty.objects.create(
        batch_subject=bs,
        faculty=faculty,
        role="primary",
        assigned_at=datetime.date(2026, 1, 1),
    )
    return subject


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    year = AcademicYearFactory(branch=branch, is_current=True)
    homeroom = BatchFactory(course__department__branch=branch, academic_year=year, name="A")
    other = BatchFactory(course__department__branch=branch, academic_year=year, name="B")
    class_teacher = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-CT2", must_change_password=False,
    )
    subject_teacher = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-ST2", must_change_password=False,
    )
    homeroom.class_teacher = class_teacher
    homeroom.save(update_fields=["class_teacher"])
    other_subject = _assign_subject_teacher(other, subject_teacher)
    homeroom_subject = _assign_subject_teacher(homeroom, subject_teacher)
    return dict(
        branch=branch,
        homeroom=homeroom,
        other=other,
        class_teacher=class_teacher,
        subject_teacher=subject_teacher,
        other_subject=other_subject,
        homeroom_subject=homeroom_subject,
    )


def _create_via_admin(env, batch, subject, faculty, title="Test"):
    bs = BatchSubject.objects.get(batch=batch, subject=subject)
    return Assignment.objects.create(
        branch=env["branch"],
        batch_subject=bs,
        title=title,
        description="",
        max_marks=25,
        due_at=timezone.now() + datetime.timedelta(days=3),
        created_by=faculty,
    )


def test_subject_teacher_creates_in_other_classes(env):
    url = reverse(URL)
    resp = _client(env["subject_teacher"]).post(url, {
        "title": "Algebra sheet",
        "description": "Ex 1-5",
        "classSectionId": str(env["other"].id),
        "subjectId": str(env["other_subject"].id),
        "dueAt": _due_at_future(),
    }, format="json")
    assert resp.status_code == 201, resp.content

    body = _data(_client(env["subject_teacher"]).get(url))
    assert len(body["otherClasses"]["assignments"]) == 1
    assert len(body["otherClasses"]["teachingClasses"]) >= 1


def test_class_teacher_cannot_create_without_subject_assignment(env):
    only_ct = UserFactory(
        role=Role.FACULTY, tenant=env["branch"].tenant, branch=env["branch"],
        custom_login_id="FAC-ONLY2", must_change_password=False,
    )
    solo = BatchFactory(
        course__department__branch=env["branch"],
        academic_year=env["homeroom"].academic_year,
        name="C",
    )
    solo.class_teacher = only_ct
    solo.save(update_fields=["class_teacher"])
    url = reverse(URL)
    subject = Subject.objects.create(course=solo.course, name="Sci", code="SC")
    period = AcademicPeriod.objects.create(
        academic_year=solo.academic_year,
        period_type=PeriodType.TERM,
        sequence=1,
        name="T1",
        start_date=datetime.date(2026, 1, 1),
        end_date=datetime.date(2026, 12, 1),
    )
    BatchSubject.objects.create(batch=solo, subject=subject, academic_period=period)
    resp = _client(only_ct).post(url, {
        "title": "Should fail",
        "classSectionId": str(solo.id),
        "subjectId": str(subject.id),
        "dueAt": _due_at_future(),
    }, format="json")
    assert resp.status_code == 403


def test_class_teacher_sees_all_assignments_in_my_class(env):
    _create_via_admin(env, env["homeroom"], env["homeroom_subject"], env["subject_teacher"], "Colleague work")
    body = _data(_client(env["class_teacher"]).get(reverse(URL)))
    titles = [a["title"] for a in body["myClass"]["assignments"]]
    assert "Colleague work" in titles
    assert len(body["myClass"]["homerooms"]) == 1
