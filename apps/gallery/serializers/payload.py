"""Gallery API payload builders."""

from __future__ import annotations

from apps.gallery.enums import AlbumVisibility
from apps.gallery.services.storage import get_gallery_storage


def album_payload(album, *, include_stats: bool = True) -> dict:
    storage = get_gallery_storage()
    created_by = album.created_by
    data = {
        "id": str(album.id),
        "title": album.title,
        "slug": album.slug,
        "description": album.description,
        "branchId": str(album.branch_id),
        "batchId": str(album.batch_id) if album.batch_id else None,
        "batchName": album.batch.name if album.batch_id else None,
        "academicYearId": str(album.academic_year_id),
        "academicYearName": album.academic_year.name,
        "visibility": album.visibility,
        "eventTag": album.event_tag,
        "sortOrder": album.sort_order,
        "isSchoolAlbum": album.is_school_album,
        "coverImageUrl": storage.resolve_cover_url(album),
        "createdAt": album.created_at.isoformat(),
        "createdByName": created_by.full_name if created_by else "",
    }
    if include_stats:
        data["totalImages"] = album.total_images
    return data


def image_payload(image) -> dict:
    storage = get_gallery_storage()
    main_url, thumb_url = storage.resolve_image_urls(image)
    uploaded_by = image.uploaded_by
    return {
        "id": str(image.id),
        "albumId": str(image.album_id),
        "imageUrl": main_url,
        "thumbnailUrl": thumb_url,
        "originalFileName": image.original_file_name,
        "fileSize": image.file_size,
        "width": image.width,
        "height": image.height,
        "sortOrder": image.sort_order,
        "processingStatus": image.processing_status,
        "processingError": image.processing_error or None,
        "uploadedByName": uploaded_by.full_name if uploaded_by else "",
        "createdAt": image.created_at.isoformat(),
    }


def visibility_allows(role: str, visibility: str) -> bool:
    if visibility == AlbumVisibility.PRIVATE:
        return False
    if visibility == AlbumVisibility.STAFF_ONLY:
        return role in ("admin", "super_admin", "faculty")
    if visibility == AlbumVisibility.FACULTY:
        return role in ("admin", "super_admin", "faculty", "student", "parent")
    if visibility == AlbumVisibility.PARENTS:
        return role in ("admin", "super_admin", "faculty", "student", "parent")
    return role in ("admin", "super_admin", "faculty", "student", "parent")
