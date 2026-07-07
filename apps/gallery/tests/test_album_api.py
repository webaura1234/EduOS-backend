"""Gallery album API tests."""

import pytest
from rest_framework.test import APIClient

from apps.academics.models import AcademicYear
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.gallery.models import GalleryAlbum
from apps.organizations.tests.factories import BranchFactory, TenantFactory


@pytest.mark.django_db
def test_admin_can_create_school_album():
    tenant = TenantFactory()
    branch = BranchFactory(tenant=tenant, code="MC")
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
            "visibility": "students",
        },
        format="json",
    )
    assert res.status_code == 201, res.content
    assert GalleryAlbum.objects.filter(branch=branch, title="Sports Day").exists()


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
        visibility="students",
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
