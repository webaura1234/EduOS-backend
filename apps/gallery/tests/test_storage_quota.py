"""Storage quota unit + API tests."""

import pytest
from rest_framework.test import APIClient

from apps.academics.models import AcademicYear
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.gallery.enums import ProcessingStatus
from apps.gallery.models import GalleryAlbum, GalleryImage
from apps.organizations.billing.storage_quota import (
    adjust_storage_usage,
    assert_can_upload,
    recompute_gallery_usage,
    storage_limit_gb_for_licenses,
    storage_status_payload,
    storage_warning_snapshot,
    sync_storage_limit_for_tenant,
    warning_level,
)
from apps.organizations.models import TenantLicenseSummary
from apps.organizations.tests.factories import BranchFactory, PlanSubscriptionFactory, TenantFactory
from rest_framework.exceptions import ValidationError


def test_storage_limit_gb_for_licenses():
    assert storage_limit_gb_for_licenses(0) == 0
    assert storage_limit_gb_for_licenses(100) == 10
    assert storage_limit_gb_for_licenses(500) == 50
    assert storage_limit_gb_for_licenses(1000) == 100
    assert storage_limit_gb_for_licenses(2500) == 250


def test_warning_level_thresholds():
    assert warning_level(0) == "none"
    assert warning_level(79.9) == "none"
    assert warning_level(80) == "warn"
    assert warning_level(89.9) == "warn"
    assert warning_level(90) == "critical"
    assert warning_level(99.9) == "critical"
    assert warning_level(100) == "blocked"
    assert warning_level(50, blocked=True) == "blocked"


@pytest.mark.django_db
def test_sync_storage_limit_from_licenses():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, storage_limit_gb=0)
    TenantLicenseSummary.objects.create(tenant=tenant, licenses_purchased=100, licenses_consumed=0)
    assert sync_storage_limit_for_tenant(tenant) == 10
    tenant.subscription.refresh_from_db()
    assert tenant.subscription.storage_limit_gb == 10


@pytest.mark.django_db
def test_assert_can_upload_blocks_when_over_limit():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, storage_limit_gb=0)
    with pytest.raises(ValidationError):
        assert_can_upload(tenant, 1000)


@pytest.mark.django_db
def test_assert_can_upload_blocks_when_usage_plus_estimate_exceeds():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, storage_limit_gb=1)  # 1 GiB
    limit = 1 * 1024 * 1024 * 1024
    adjust_storage_usage(tenant, limit - 1000)
    assert_can_upload(tenant, 500)  # still under
    with pytest.raises(ValidationError) as exc:
        assert_can_upload(tenant, 2000)
    assert "storage" in exc.value.detail


@pytest.mark.django_db
def test_storage_soft_warnings_in_payload():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, storage_limit_gb=1)
    limit = 1 * 1024 * 1024 * 1024

    adjust_storage_usage(tenant, int(limit * 0.85))
    snap = storage_warning_snapshot(tenant)
    assert snap["warningLevel"] == "warn"
    assert "80%" in (snap["message"] or "")

    adjust_storage_usage(tenant, int(limit * 0.10))  # ~95%
    snap = storage_warning_snapshot(tenant)
    assert snap["warningLevel"] == "critical"
    assert "10%" in (snap["message"] or "")


@pytest.mark.django_db
def test_storage_usage_endpoint():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, storage_limit_gb=10)
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, must_change_password=False)
    client = APIClient()
    client.force_authenticate(user=admin)
    res = client.get("/api/v1/gallery/storage/")
    assert res.status_code == 200, res.content
    body = res.json().get("data", res.json())
    assert body["limitBytes"] == 10 * 1024 * 1024 * 1024
    assert body["usedBytes"] == 0
    assert body["warningLevel"] == "none"
    assert body["stats"]["totalImages"] == 0
    assert body["stats"]["albums"] == 0
    assert body["stats"]["lastUploadAt"] is None
    assert body["stats"]["largestAlbum"] is None
    assert body["breakdown"]["galleryBytes"] == 0
    assert body["breakdown"]["documentsBytes"] == 0
    assert body["breakdown"]["exportsBytes"] == 0


@pytest.mark.django_db
def test_presign_rejects_when_storage_full():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, storage_limit_gb=0)
    branch = BranchFactory(tenant=tenant, code="MC")
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, must_change_password=False)
    from datetime import date
    year = AcademicYear.objects.create(
        branch=branch, name="2025-26",
        start_date=date(2025, 6, 1), end_date=date(2026, 4, 30), is_current=True,
    )
    album = GalleryAlbum.objects.create(
        branch=branch, academic_year=year, title="Full", slug="full",
        created_by=admin, updated_by=admin,
    )
    client = APIClient()
    client.force_authenticate(user=admin)
    res = client.post(
        "/api/v1/gallery/images/presign/",
        {
            "albumId": str(album.pk),
            "files": [{"fileName": "photo.jpg", "contentType": "image/jpeg", "fileSize": 5000}],
        },
        format="json",
    )
    assert res.status_code == 400, res.content


@pytest.mark.django_db
def test_presign_includes_storage_soft_warning():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, storage_limit_gb=1)
    branch = BranchFactory(tenant=tenant, code="MC")
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, must_change_password=False)
    limit = 1 * 1024 * 1024 * 1024
    adjust_storage_usage(tenant, int(limit * 0.82))
    from datetime import date
    year = AcademicYear.objects.create(
        branch=branch, name="2025-26",
        start_date=date(2025, 6, 1), end_date=date(2026, 4, 30), is_current=True,
    )
    album = GalleryAlbum.objects.create(
        branch=branch, academic_year=year, title="Warn", slug="warn",
        created_by=admin, updated_by=admin,
    )
    client = APIClient()
    client.force_authenticate(user=admin)
    res = client.post(
        "/api/v1/gallery/images/presign/",
        {
            "albumId": str(album.pk),
            "files": [{"fileName": "photo.jpg", "contentType": "image/jpeg", "fileSize": 1000}],
        },
        format="json",
    )
    assert res.status_code == 200, res.content
    body = res.json().get("data", res.json())
    assert body["storage"]["warningLevel"] == "warn"
    assert body["storage"]["message"]


@pytest.mark.django_db
def test_recompute_gallery_usage():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, storage_limit_gb=5)
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, must_change_password=False)
    from datetime import date
    year = AcademicYear.objects.create(
        branch=branch, name="2025-26",
        start_date=date(2025, 6, 1), end_date=date(2026, 4, 30), is_current=True,
    )
    album = GalleryAlbum.objects.create(
        branch=branch, academic_year=year, title="A", slug="a",
        created_by=admin, updated_by=admin,
    )
    GalleryImage.objects.create(
        album=album,
        processing_status=ProcessingStatus.READY,
        stored_bytes=1500,
        created_by=admin,
        updated_by=admin,
    )
    assert recompute_gallery_usage(tenant) == 1500
    status = storage_status_payload(tenant)
    assert status["usedBytes"] == 1500
    assert status["stats"]["totalImages"] == 1
    assert status["stats"]["largestAlbum"]["title"] == "A"
