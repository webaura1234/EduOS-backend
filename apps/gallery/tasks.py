"""Celery tasks for gallery image processing."""

from __future__ import annotations

import datetime

from celery import shared_task
from django.conf import settings
from django.utils import timezone

from apps.gallery.models import GalleryImage
from apps.gallery.services.storage import get_gallery_storage


@shared_task(bind=True, max_retries=3, default_retry_delay=30)
def process_gallery_upload(self, image_id: str) -> None:
    from apps.gallery.interactors.image import process_image_record
    try:
        process_image_record(image_id)
    except Exception as exc:
        raise self.retry(exc=exc) from exc


@shared_task
def purge_stale_gallery_staging() -> int:
    """Delete staging objects older than GALLERY_STAGING_TTL_HOURS."""
    storage = get_gallery_storage()
    ttl_hours = getattr(settings, "GALLERY_STAGING_TTL_HOURS", 24)
    cutoff = timezone.now() - datetime.timedelta(hours=ttl_hours)
    deleted = 0
    for image in GalleryImage.objects.filter(
        staging_key__gt="",
        processing_status__in=("pending", "failed"),
        created_at__lt=cutoff,
        is_active=True,
    ):
        storage.delete_file(key=image.staging_key)
        image.staging_key = ""
        image.save(update_fields=["staging_key", "updated_at"])
        deleted += 1
    return deleted
