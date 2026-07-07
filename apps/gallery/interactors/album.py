"""Album interactors."""

from __future__ import annotations

from django.utils.text import slugify
from rest_framework.exceptions import ValidationError

from apps.gallery.models import GalleryAlbum, GalleryImage
from apps.gallery.queries import album as album_q
from apps.gallery.queries import image as image_q
from apps.gallery.services.storage import get_gallery_storage


def _unique_slug(branch_id, title: str, *, batch_id=None, exclude_id=None) -> str:
    base = slugify(title)[:100] or "album"
    slug = base
    n = 2
    while album_q.slug_exists(branch_id, slug, batch_id=batch_id, exclude_id=exclude_id):
        slug = f"{base}-{n}"
        n += 1
    return slug


def create_album(*, branch, academic_year, title, user, batch=None, description="", visibility="students", event_tag=""):
    title = (title or "").strip()
    if not title:
        raise ValidationError({"title": "Title is required."})
    slug = _unique_slug(branch.pk, title, batch_id=batch.pk if batch else None)
    return GalleryAlbum.objects.create(
        branch=branch,
        batch=batch,
        academic_year=academic_year,
        title=title,
        slug=slug,
        description=(description or "").strip(),
        visibility=visibility or "students",
        event_tag=(event_tag or "").strip(),
        created_by=user,
        updated_by=user,
    )


def update_album(album: GalleryAlbum, *, user, **fields) -> GalleryAlbum:
    if "title" in fields and fields["title"]:
        album.title = fields["title"].strip()
        album.slug = _unique_slug(
            album.branch_id, album.title,
            batch_id=album.batch_id, exclude_id=album.pk,
        )
    if "description" in fields:
        album.description = (fields["description"] or "").strip()
    if "visibility" in fields and fields["visibility"]:
        album.visibility = fields["visibility"]
    if "event_tag" in fields:
        album.event_tag = (fields["event_tag"] or "").strip()
    if "sort_order" in fields and fields["sort_order"] is not None:
        album.sort_order = int(fields["sort_order"])
    album.updated_by = user
    album.save()
    return album


def delete_album(album: GalleryAlbum, *, user) -> None:
    storage = get_gallery_storage()
    prefix = storage.build_album_prefix(
        branch=album.branch, batch=album.batch, album_slug=album.slug,
    ) + "/"
    storage.delete_folder(prefix=prefix)
    for image in image_q.list_for_album(album.pk):
        image.soft_delete(user=user)
    album.soft_delete(user=user)


def set_cover(album: GalleryAlbum, image_id, *, user) -> GalleryAlbum:
    image = image_q.get_for_album(album.pk, image_id)
    if image.processing_status != "ready" or not image.image_key:
        raise ValidationError({"imageId": "Image is not ready."})
    album.cover_image_key = image.thumbnail_key or image.image_key
    album.updated_by = user
    album.save(update_fields=["cover_image_key", "updated_by", "updated_at"])
    return album


def reorder_images(album: GalleryAlbum, image_ids: list, *, user) -> None:
    images = {str(i.pk): i for i in image_q.get_by_ids(album.pk, image_ids)}
    for order, image_id in enumerate(image_ids):
        img = images.get(str(image_id))
        if img is None:
            raise ValidationError({"imageIds": f"Unknown image: {image_id}"})
        img.sort_order = order
        img.updated_by = user
    GalleryImage.objects.bulk_update(
        list(images.values()), ["sort_order", "updated_by", "updated_at"],
    )


def refresh_total_images(album_id) -> None:
    count = image_q.list_for_album(album_id, ready_only=True).count()
    GalleryAlbum.objects.filter(pk=album_id).update(total_images=count)
