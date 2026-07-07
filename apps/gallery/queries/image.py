"""Image queries."""

from __future__ import annotations

from django.db.models import Max, QuerySet

from apps.gallery.models import GalleryImage


def list_for_album(album_id, *, ready_only: bool = False) -> QuerySet:
    qs = GalleryImage.objects.filter(album_id=album_id, is_active=True).select_related("uploaded_by")
    if ready_only:
        qs = qs.filter(processing_status="ready")
    return qs.order_by("sort_order", "-created_at")


def paginate_for_album(album_id, *, page: int = 1, page_size: int = 48, ready_only: bool = False):
    qs = list_for_album(album_id, ready_only=ready_only)
    total = qs.count()
    offset = max(page - 1, 0) * page_size
    items = list(qs[offset : offset + page_size])
    return items, total


def get_for_album(album_id, image_id) -> GalleryImage:
    return GalleryImage.objects.select_related("album", "uploaded_by").get(
        pk=image_id, album_id=album_id, is_active=True,
    )


def get_by_ids(album_id, image_ids: list) -> list[GalleryImage]:
    return list(
        GalleryImage.objects.filter(
            album_id=album_id, pk__in=image_ids, is_active=True,
        ).order_by("sort_order", "-created_at"),
    )


def next_sort_order(album_id) -> int:
    current = GalleryImage.objects.filter(album_id=album_id, is_active=True).aggregate(
        m=Max("sort_order"),
    )["m"]
    return (current or 0) + 1


def duplicate_hash_exists(album_id, content_hash: str) -> bool:
    if not content_hash:
        return False
    return GalleryImage.objects.filter(
        album_id=album_id, content_hash=content_hash, is_active=True,
    ).exists()
