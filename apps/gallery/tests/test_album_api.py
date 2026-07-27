"""Gallery album API tests."""

import pytest
from rest_framework.test import APIClient

from apps.academics.models import AcademicYear
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.gallery.models import GalleryAlbum
from apps.gallery.services.visibility import visibility_allows
from apps.organizations.tests.factories import BranchFactory, PlanSubscriptionFactory, TenantFactory


@pytest.mark.django_db
def test_admin_can_create_school_album():
    tenant = TenantFactory()
    branch = BranchFactory(tenant=tenant, code="MC")
    PlanSubscriptionFactory(tenant=tenant, storage_limit_gb=10)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, must_change_password=False)
    year = AcademicYear.objects.filter(branch=branch).first()
    if year is None:
        from datetime import date
        year = AcademicYear.objects.create(
            branch=branch, name="2025-26",
            start_date=date(2025, 6, 1), end_date=date(2026, 4, 30), is_current=True,
        )
    client = APIClient()
    client.force_authenticate(user=admin)
    res = client.post(
        "/api/v1/gallery/albums/",
        {
            "title": "Sports Day",
            "description": "Annual sports",
            "academicYearId": str(year.pk),
            "visibility": ["students", "parents"],
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    album = GalleryAlbum.objects.get(branch=branch, title="Sports Day")
    assert album.visibility == ["students", "parents"]
    body = res.json()
    payload = body.get("data", body)
    assert payload["visibility"] == ["students", "parents"]


@pytest.mark.django_db
def test_student_can_list_visible_albums():
    tenant = TenantFactory()
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, must_change_password=False)
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-99")
    year = AcademicYear.objects.filter(branch=branch).first()
    if year is None:
        from datetime import date
        year = AcademicYear.objects.create(
            branch=branch, name="2025-26",
            start_date=date(2025, 6, 1), end_date=date(2026, 4, 30), is_current=True,
        )
    GalleryAlbum.objects.create(
        branch=branch,
        academic_year=year,
        title="Open Album",
        slug="open-album",
        visibility=["students"],
        created_by=admin,
        updated_by=admin,
    )
    client = APIClient()
    client.force_authenticate(user=student)
    res = client.get("/api/v1/gallery/albums/me/")
    assert res.status_code == 200
    body = res.json()
    data = body.get("data", body)
    assert len(data["albums"]) >= 1


@pytest.mark.django_db
def test_multi_audience_filters_reader_roles():
    tenant = TenantFactory()
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, must_change_password=False)
    student = UserFactory(role=Role.STUDENT, tenant=tenant, branch=branch, custom_login_id="STU-100")
    parent = UserFactory(role=Role.PARENT, tenant=tenant, branch=branch)
    faculty = UserFactory(role=Role.FACULTY, tenant=tenant, branch=branch)
    year = AcademicYear.objects.filter(branch=branch).first()
    if year is None:
        from datetime import date
        year = AcademicYear.objects.create(
            branch=branch, name="2025-26",
            start_date=date(2025, 6, 1), end_date=date(2026, 4, 30), is_current=True,
        )
    GalleryAlbum.objects.create(
        branch=branch,
        academic_year=year,
        title="Parents and Faculty",
        slug="parents-faculty",
        visibility=["parents", "faculty"],
        created_by=admin,
        updated_by=admin,
    )
    GalleryAlbum.objects.create(
        branch=branch,
        academic_year=year,
        title="Private",
        slug="private-album",
        visibility=[],
        created_by=admin,
        updated_by=admin,
    )

    def album_titles(user):
        client = APIClient()
        client.force_authenticate(user=user)
        res = client.get("/api/v1/gallery/albums/me/")
        assert res.status_code == 200
        body = res.json()
        data = body.get("data", body)
        return {a["title"] for a in data["albums"]}

    assert "Parents and Faculty" not in album_titles(student)
    assert "Parents and Faculty" in album_titles(parent)
    assert "Parents and Faculty" in album_titles(faculty)
    assert "Private" not in album_titles(student)
    assert "Private" not in album_titles(parent)
    assert "Private" not in album_titles(faculty)


def test_visibility_allows_unit():
    assert visibility_allows("student", ["students", "faculty"])
    assert not visibility_allows("parent", ["students", "faculty"])
    assert visibility_allows("faculty", ["students", "faculty"])
    assert not visibility_allows("student", [])
    assert visibility_allows("admin", [])
    assert visibility_allows("student", "students")  # legacy string
    assert visibility_allows("faculty", "staff_only")
