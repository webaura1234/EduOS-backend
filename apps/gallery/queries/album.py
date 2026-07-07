"""Album queries."""

from __future__ import annotations

import datetime

from django.db.models import Q, QuerySet

from apps.gallery.models import GalleryAlbum


def list_for_branch(
    branch_id,
    *,
    batch_id=None,
    academic_year_id=None,
    event_tag: str | None = None,
    search: str | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
    school_only: bool | None = None,
) -> QuerySet:
    qs = (
        GalleryAlbum.objects.filter(branch_id=branch_id, is_active=True)
        .select_related("batch", "batch__course", "academic_year", "created_by")
    )
    if batch_id:
        qs = qs.filter(batch_id=batch_id)
    if school_only:
        qs = qs.filter(batch__isnull=True)
    if academic_year_id:
        qs = qs.filter(academic_year_id=academic_year_id)
    if event_tag:
        qs = qs.filter(event_tag__iexact=event_tag)
    if search:
        q = search.strip()
        qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(event_tag__icontains=q))
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)
    return qs.order_by("sort_order", "-created_at")


def get_for_branch(branch_id, album_id) -> GalleryAlbum:
    return GalleryAlbum.objects.select_related(
        "batch", "batch__course", "academic_year", "created_by", "branch",
    ).get(pk=album_id, branch_id=branch_id, is_active=True)


def slug_exists(branch_id, slug: str, *, batch_id=None, exclude_id=None) -> bool:
    qs = GalleryAlbum.objects.filter(branch_id=branch_id, slug=slug, is_active=True)
    if batch_id:
        qs = qs.filter(batch_id=batch_id)
    else:
        qs = qs.filter(batch__isnull=True)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()
