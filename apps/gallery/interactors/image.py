"""Image upload and management interactors."""

from __future__ import annotations

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.gallery.enums import ProcessingStatus
from apps.gallery.models import GalleryImage
from apps.gallery.queries import album as album_q
from apps.gallery.queries import image as image_q
from apps.gallery.services.image_pipeline import process_image, validate_upload_meta
from apps.gallery.services.storage import get_gallery_storage


def presign_uploads(*, album, files: list[dict], user) -> list[dict]:
    storage = get_gallery_storage()
    results = []
    for spec in files:
        file_name = (spec.get("fileName") or "").strip()
        content_type = (spec.get("contentType") or "").strip()
        file_size = int(spec.get("fileSize") or 0)
        validate_upload_meta(file_name=file_name, content_type=content_type, file_size=file_size)

        staging_key = storage.generate_staging_key()
        image = GalleryImage.objects.create(
            album=album,
            staging_key=staging_key,
            original_file_name=file_name,
            file_size=file_size,
            sort_order=image_q.next_sort_order(album.pk),
            processing_status=ProcessingStatus.PENDING,
            uploaded_by=user,
            created_by=user,
            updated_by=user,
        )
        presigned_url = storage.presigned_upload_url(key=staging_key, content_type=content_type)
        results.append({
            "imageId": str(image.pk),
            "stagingKey": staging_key,
            "presignedUrl": presigned_url,
        })
    return results


def confirm_upload(*, album, image_id, user, sync_process: bool = False) -> GalleryImage:
    image = image_q.get_for_album(album.pk, image_id)
    if not image.staging_key:
        raise ValidationError({"imageId": "No staging upload for this image."})
    if sync_process:
        from apps.gallery.tasks import process_gallery_upload
        process_gallery_upload(str(image.pk))
        image.refresh_from_db()
    else:
        from apps.gallery.tasks import process_gallery_upload
        process_gallery_upload.delay(str(image.pk))
    return image


def process_image_record(image_id: str) -> None:
    """Download staging object, process, upload final keys, update DB."""
    storage = get_gallery_storage()
    image = GalleryImage.objects.select_related("album", "album__branch", "album__batch").get(pk=image_id)
    album = image.album

    if not image.staging_key:
        if image.external_url:
            image.processing_status = ProcessingStatus.READY
            image.save(update_fields=["processing_status", "updated_at"])
            return
        raise ValidationError("Missing staging key.")

    try:
        raw = storage.download_file(key=image.staging_key)
        main_bytes, thumb_bytes, width, height, content_hash = process_image(raw)

        if image_q.duplicate_hash_exists(album.pk, content_hash):
            storage.delete_file(key=image.staging_key)
            image.processing_status = ProcessingStatus.FAILED
            image.processing_error = "Duplicate image already exists in this album."
            image.save(update_fields=["processing_status", "processing_error", "updated_at"])
            return

        image_uuid = image.pk.hex[:12]
        main_key, thumb_key = storage.build_image_keys(
            branch=album.branch,
            batch=album.batch,
            album_slug=album.slug,
            image_uuid=image_uuid,
        )
        storage.upload_file(key=main_key, content=main_bytes, content_type="image/webp")
        storage.upload_file(key=thumb_key, content=thumb_bytes, content_type="image/webp")
        storage.delete_file(key=image.staging_key)

        image.image_key = main_key
        image.thumbnail_key = thumb_key
        image.staging_key = ""
        image.width = width
        image.height = height
        image.content_hash = content_hash
        image.processing_status = ProcessingStatus.READY
        image.processing_error = ""
        image.save()

        if not album.cover_image_key:
            album.cover_image_key = thumb_key
            album.save(update_fields=["cover_image_key", "updated_at"])

        from apps.gallery.interactors.album import refresh_total_images
        refresh_total_images(album.pk)
    except Exception as exc:
        image.processing_status = ProcessingStatus.FAILED
        image.processing_error = str(exc)[:500]
        image.save(update_fields=["processing_status", "processing_error", "updated_at"])
        raise


def bulk_delete_images(*, album, image_ids: list, user) -> int:
    storage = get_gallery_storage()
    deleted = 0
    for image in image_q.get_by_ids(album.pk, image_ids):
        storage.delete_file(key=image.image_key)
        storage.delete_file(key=image.thumbnail_key)
        image.soft_delete(user=user)
        deleted += 1
    if album.cover_image_key and not image_q.list_for_album(album.pk, ready_only=True).exists():
        album.cover_image_key = ""
        album.save(update_fields=["cover_image_key", "updated_at"])
    else:
        first = image_q.list_for_album(album.pk, ready_only=True).first()
        if first and album.cover_image_key:
            keys = {album.cover_image_key}
            if not any(i.thumbnail_key in keys or i.image_key in keys for i in image_q.list_for_album(album.pk, ready_only=True)):
                album.cover_image_key = first.thumbnail_key or first.image_key
                album.save(update_fields=["cover_image_key", "updated_at"])
    from apps.gallery.interactors.album import refresh_total_images
    refresh_total_images(album.pk)
    return deleted


def move_images(*, source_album, target_album, image_ids: list, user) -> int:
    if source_album.branch_id != target_album.branch_id:
        raise ValidationError({"targetAlbumId": "Albums must belong to the same branch."})
    storage = get_gallery_storage()
    moved = 0
    with transaction.atomic():
        for image in image_q.get_by_ids(source_album.pk, image_ids):
            if image.processing_status != ProcessingStatus.READY:
                continue
            new_main, new_thumb = storage.build_image_keys(
                branch=target_album.branch,
                batch=target_album.batch,
                album_slug=target_album.slug,
            )
            if image.image_key:
                storage.move_file(source_key=image.image_key, dest_key=new_main)
            if image.thumbnail_key:
                storage.move_file(source_key=image.thumbnail_key, dest_key=new_thumb)
            image.image_key = new_main
            image.thumbnail_key = new_thumb
            image.album = target_album
            image.sort_order = image_q.next_sort_order(target_album.pk)
            image.updated_by = user
            image.save()
            moved += 1
        from apps.gallery.interactors.album import refresh_total_images
        refresh_total_images(source_album.pk)
        refresh_total_images(target_album.pk)
    return moved


def retry_processing(image_id: str) -> GalleryImage:
    from apps.gallery.tasks import process_gallery_upload
    image = GalleryImage.objects.get(pk=image_id)
    image.processing_status = ProcessingStatus.PENDING
    image.processing_error = ""
    image.save(update_fields=["processing_status", "processing_error", "updated_at"])
    process_gallery_upload.delay(image_id)
    return image
