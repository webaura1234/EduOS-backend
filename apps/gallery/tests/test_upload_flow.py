"""Upload flow tests using SandboxS3."""

import pytest
from rest_framework.test import APIClient

from apps.academics.models import AcademicYear
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.gallery.models import GalleryAlbum, GalleryImage
from apps.gallery.tasks import process_gallery_upload
from apps.integrations.adapters.s3 import SandboxS3
from apps.organizations.tests.factories import BranchFactory, PlanSubscriptionFactory, TenantFactory
from apps.gallery.tests.test_image_pipeline import _jpeg_bytes


@pytest.mark.django_db
def test_presign_confirm_process_flow():
    SandboxS3.SINK.clear()
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, storage_limit_gb=10)
    branch = BranchFactory(tenant=tenant, code="MC")
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch, must_change_password=False)
    from datetime import date
    year = AcademicYear.objects.create(
        branch=branch, name="2025-26",
        start_date=date(2025, 6, 1), end_date=date(2026, 4, 30), is_current=True,
    )
    album = GalleryAlbum.objects.create(
        branch=branch, academic_year=year, title="Test", slug="test",
        created_by=admin, updated_by=admin,
    )
    client = APIClient()
    client.force_authenticate(user=admin)
    presign = client.post(
        "/api/v1/gallery/images/presign/",
        {
            "albumId": str(album.pk),
            "files": [{"fileName": "photo.jpg", "contentType": "image/jpeg", "fileSize": 5000}],
        },
        format="json",
    )
    assert presign.status_code == 200, presign.content
    upload = presign.json().get("data", presign.json())["uploads"][0]
    image = GalleryImage.objects.get(pk=upload["imageId"])
    SandboxS3.SINK[image.staging_key] = _jpeg_bytes()

    process_gallery_upload(str(image.pk))
    image.refresh_from_db()
    assert image.processing_status == "ready"
    assert image.image_key.endswith(".webp")
    assert image.thumbnail_key.endswith(".webp")

    from urllib.parse import urlparse

    from apps.gallery.serializers.payload import image_payload

    payload = image_payload(image)
    assert payload["thumbnailUrl"]
    assert "/api/v1/gallery/media/" in payload["thumbnailUrl"]
    assert "sig=" in payload["thumbnailUrl"]

    parsed = urlparse(payload["thumbnailUrl"])
    media = client.get(f"{parsed.path}?{parsed.query}")
    assert media.status_code == 200
    assert media["Content-Type"] == "image/webp"
    assert len(media.content) > 100


@pytest.mark.django_db
def test_sandbox_media_rejects_bad_signature():
    client = APIClient()
    resp = client.get("/api/v1/gallery/media/?key=staging/x&exp=9999999999&sig=deadbeef")
    assert resp.status_code == 403
