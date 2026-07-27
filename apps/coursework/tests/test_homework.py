"""Homework — faculty assign/list + student published feed."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models.calendar import AcademicPeriod, PeriodType
from apps.academics.models.curriculum import BatchFaculty, BatchSubject, Subject
from apps.academics.tests.factories import AcademicYearFactory, BatchFactory
from apps.accounts.models.profile import StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.tests.factories import StudentEnrollmentFactory
from apps.coursework import queries as hw_q
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def _assign_subject_teacher(batch, faculty, branch):
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
    homeroom_batch = BatchFactory(course__department__branch=branch, academic_year=year, name="A")
    other_batch = BatchFactory(course__department__branch=branch, academic_year=year, name="B")
    class_teacher = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-CT", must_change_password=False,
    )
    subject_teacher = UserFactory(
        role=Role.FACULTY, tenant=tenant, branch=branch,
        custom_login_id="FAC-ST", must_change_password=False,
    )
    homeroom_batch.class_teacher = class_teacher
    homeroom_batch.save(update_fields=["class_teacher"])
    _assign_subject_teacher(other_batch, subject_teacher, branch)
    _assign_subject_teacher(homeroom_batch, subject_teacher, branch)

    su = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch,
                     custom_login_id="STU-1", must_change_password=False)
    profile = StudentProfile.objects.create(user=su, current_batch=homeroom_batch)
    StudentEnrollmentFactory(student_profile=profile, branch=branch, batch=homeroom_batch)
    return dict(
        branch=branch,
        homeroom_batch=homeroom_batch,
        other_batch=other_batch,
        class_teacher=class_teacher,
        subject_teacher=subject_teacher,
        student=su,
    )


def test_subject_teacher_assign_and_list_homework(env):
    url = reverse("coursework:faculty-homework")
    resp = _client(env["subject_teacher"]).post(url, {
        "classSectionId": str(env["other_batch"].id),
        "date": "2026-06-22",
        "title": "Read chapter 4",
        "details": "Pages 40-55",
        "publish": True,
    }, format="json")
    assert resp.status_code == 201, resp.content
    entry = _data(resp)["entry"]
    assert entry["status"] == "published" and entry["classLabel"]

    body = _data(_client(env["subject_teacher"]).get(url))
    assert body["canAssign"] is True
    assert len(body["otherClasses"]["teachingClasses"]) >= 1
    assert len(body["otherClasses"]["homework"]) == 1


def test_class_teacher_cannot_post_without_subject_assignment(env):
    """Class teacher alone cannot create homework — needs BatchFaculty."""
    only_ct = UserFactory(
        role=Role.FACULTY, tenant=env["branch"].tenant, branch=env["branch"],
        custom_login_id="FAC-ONLY-CT", must_change_password=False,
    )
    solo_batch = BatchFactory(
        course__department__branch=env["branch"],
        academic_year=env["homeroom_batch"].academic_year,
        name="C",
    )
    solo_batch.class_teacher = only_ct
    solo_batch.save(update_fields=["class_teacher"])
    url = reverse("coursework:faculty-homework")
    resp = _client(only_ct).post(url, {
        "classSectionId": str(solo_batch.id),
        "date": "2026-06-22",
        "title": "Should fail",
        "publish": True,
    }, format="json")
    assert resp.status_code == 403


def test_class_teacher_sees_all_homework_in_my_class(env):
    url = reverse("coursework:faculty-homework")
    hw_q.create(
        branch=env["branch"], batch=env["homeroom_batch"], date=datetime.date(2026, 6, 22),
        title="From colleague", details="", publish=True, user=env["subject_teacher"],
    )
    body = _data(_client(env["class_teacher"]).get(url))
    titles = [h["title"] for h in body["myClass"]["homework"]]
    assert "From colleague" in titles
    assert len(body["myClass"]["homerooms"]) == 1


def test_class_teacher_can_delete_colleague_homework_in_homeroom(env):
    url = reverse("coursework:faculty-homework")
    hw = hw_q.create(
        branch=env["branch"], batch=env["homeroom_batch"], date=datetime.date(2026, 6, 22),
        title="To delete", details="", publish=True, user=env["subject_teacher"],
    )
    detail_url = reverse("coursework:faculty-homework-detail", kwargs={"homework_id": hw.id})
    resp = _client(env["class_teacher"]).delete(detail_url)
    assert resp.status_code == 200


def test_student_sees_only_published_for_their_batch(env):
    url = reverse("coursework:faculty-homework")
    fc = _client(env["subject_teacher"])
    fc.post(url, {
        "classSectionId": str(env["homeroom_batch"].id),
        "date": "2026-06-22",
        "title": "Published",
        "publish": True,
    }, format="json")
    fc.post(url, {
        "classSectionId": str(env["homeroom_batch"].id),
        "date": "2026-06-22",
        "title": "Draft",
        "publish": False,
    }, format="json")

    body = _data(_client(env["student"]).get(reverse("coursework:student-homework")))
    titles = [h["title"] for h in body["homework"]]
    assert titles == ["Published"]


def test_admin_can_post_homework_without_subject_assignment(env):
    admin = UserFactory(
        role=Role.ADMIN,
        tenant=env["branch"].tenant,
        branch=env["branch"],
        must_change_password=False,
    )
    url = reverse("coursework:faculty-homework")
    resp = _client(admin).post(url, {
        "classSectionId": str(env["homeroom_batch"].id),
        "date": "2026-06-22",
        "title": "Admin posted",
        "details": "For all students in class",
        "publish": True,
    }, format="json")
    assert resp.status_code == 201, resp.content
    entry = _data(resp)["entry"]
    assert entry["status"] == "published"

    body = _data(_client(env["student"]).get(reverse("coursework:student-homework")))
    titles = [h["title"] for h in body["homework"]]
    assert "Admin posted" in titles


def test_edit_existing_homework(env):
    url = reverse("coursework:faculty-homework")
    fc = _client(env["subject_teacher"])
    created = _data(fc.post(url, {
        "classSectionId": str(env["other_batch"].id),
        "date": "2026-06-22",
        "title": "Old",
        "publish": False,
    }, format="json"))["entry"]
    edited = _data(fc.post(url, {
        "id": created["id"],
        "classSectionId": str(env["other_batch"].id),
        "date": "2026-06-22",
        "title": "New",
        "publish": True,
    }, format="json"))["entry"]
    assert edited["id"] == created["id"]
    assert edited["title"] == "New" and edited["status"] == "published"


def test_student_homework_uses_enrollment_batch_branch(env):
    """Student feed resolves batch from enrollment, not the request user's branch alone."""
    url = reverse("coursework:faculty-homework")
    _client(env["subject_teacher"]).post(url, {
        "classSectionId": str(env["homeroom_batch"].id),
        "date": "2026-06-22",
        "title": "For homeroom",
        "publish": True,
    }, format="json")
    body = _data(_client(env["student"]).get(reverse("coursework:student-homework")))
    titles = [h["title"] for h in body["homework"]]
    assert "For homeroom" in titles


def test_student_homework_not_visible_for_other_branch_batch(env):
    """Homework posted to another campus batch does not appear for this student."""
    other_branch = BranchFactory(tenant=env["branch"].tenant, code="OB", name="Other Campus")
    year = env["homeroom_batch"].academic_year
    other_batch = BatchFactory(course__department__branch=other_branch, academic_year=year, name="A")
    other_teacher = UserFactory(
        role=Role.FACULTY, tenant=env["branch"].tenant, branch=other_branch,
        custom_login_id="FAC-OB", must_change_password=False,
    )
    _assign_subject_teacher(other_batch, other_teacher, other_branch)
    url = reverse("coursework:faculty-homework")
    _client(other_teacher).post(url, {
        "classSectionId": str(other_batch.id),
        "date": "2026-06-22",
        "title": "Other campus only",
        "publish": True,
    }, format="json")
    body = _data(_client(env["student"]).get(reverse("coursework:student-homework")))
    titles = [h["title"] for h in body["homework"]]
    assert "Other campus only" not in titles


def test_student_homework_falls_back_to_current_batch_without_enrollment(env):
    """Profiles with current_batch but no enrollment row still receive published homework."""
    su = UserFactory(
        role=Role.STUDENT, tenant=env["branch"].tenant, branch=env["branch"],
        custom_login_id="STU-NO-ENR", must_change_password=False,
    )
    StudentProfile.objects.create(user=su, current_batch=env["homeroom_batch"])
    url = reverse("coursework:faculty-homework")
    _client(env["subject_teacher"]).post(url, {
        "classSectionId": str(env["homeroom_batch"].id),
        "date": "2026-06-22",
        "title": "Profile batch fallback",
        "publish": True,
    }, format="json")
    body = _data(_client(su).get(reverse("coursework:student-homework")))
    titles = [h["title"] for h in body["homework"]]
    assert "Profile batch fallback" in titles


def test_homework_post_maps_to_current_academic_year_batch(env):
    """Posting against a prior-year batch id lands on the current year's section."""
    from apps.academics.models import AcademicYear

    old_year = env["homeroom_batch"].academic_year
    old_year.is_current = False
    old_year.save(update_fields=["is_current"])
    new_year = AcademicYear.objects.create(
        branch=env["branch"],
        name="2027-2028",
        start_date=datetime.date(2027, 6, 1),
        end_date=datetime.date(2028, 4, 30),
        is_current=True,
    )
    new_batch = BatchFactory(
        course=env["homeroom_batch"].course,
        academic_year=new_year,
        name=env["homeroom_batch"].name,
    )
    _assign_subject_teacher(new_batch, env["subject_teacher"], env["branch"])
    StudentEnrollmentFactory(
        student_profile=env["student"].student_profile,
        branch=env["branch"],
        batch=new_batch,
    )
    env["student"].student_profile.current_batch = new_batch
    env["student"].student_profile.save(update_fields=["current_batch"])

    url = reverse("coursework:faculty-homework")
    resp = _client(env["subject_teacher"]).post(url, {
        "classSectionId": str(env["homeroom_batch"].id),
        "date": "2026-06-22",
        "title": "Current year mapped",
        "publish": True,
    }, format="json")
    assert resp.status_code == 201, resp.content
    entry = _data(resp)["entry"]
    assert entry["classSectionId"] == str(new_batch.id)

    body = _data(_client(env["student"]).get(reverse("coursework:student-homework")))
    titles = [h["title"] for h in body["homework"]]
    assert "Current year mapped" in titles
