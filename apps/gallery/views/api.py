"""Gallery REST API views."""

from __future__ import annotations

import datetime
import mimetypes

from django.core.exceptions import ObjectDoesNotExist
from django.http import HttpResponse
from rest_framework import status as http
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import AcademicYear, Batch
from apps.academics.scoping import resolve_branch
from apps.accounts.models.user import Role
from apps.accounts.permissions import IsAdminOrSuperAdmin, IsParent, IsStudent
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.gallery.interactors import album as album_i
from apps.gallery.interactors import image as image_i
from apps.gallery.queries import album as album_q
from apps.gallery.queries import image as image_q
from apps.gallery.serializers.payload import album_payload, image_payload, visibility_allows
from apps.gallery.services.image_pipeline import validate_upload_meta
from apps.gallery.services.keys import validate_key
from apps.gallery.services.media_urls import verify_media_sig
from apps.gallery.services.storage import get_gallery_storage
from apps.integrations.adapters.s3 import S3NotFoundError


def _parse_date(value):
    if not value:
        return None
    return datetime.date.fromisoformat(value)


class GalleryMediaView(APIView):
    """Stream gallery object bytes via HMAC-signed URL (sandbox / img-src friendly)."""

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request) -> HttpResponse:
        key = request.query_params.get("key") or ""
        exp = request.query_params.get("exp") or ""
        sig = request.query_params.get("sig") or ""
        if not verify_media_sig(key=key, exp=exp, sig=sig):
            raise PermissionDenied("Invalid or expired media signature.")
        try:
            validate_key(key)
        except ValueError as exc:
            raise ValidationError({"key": str(exc)}) from exc
        storage = get_gallery_storage()
        try:
            content = storage.download_file(key=key)
        except S3NotFoundError as exc:
            raise NotFound("Media object not found.") from exc
        content_type = mimetypes.guess_type(key)[0] or "application/octet-stream"
        if key.endswith(".webp"):
            content_type = "image/webp"
        response = HttpResponse(content, content_type=content_type)
        response["Cache-Control"] = "private, max-age=3600"
        return response


class AdminAlbumListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        page = max(int(request.query_params.get("page", 1)), 1)
        page_size = min(int(request.query_params.get("pageSize", 24)), 100)
        qs = album_q.list_for_branch(
            branch.pk,
            batch_id=request.query_params.get("batchId") or None,
            academic_year_id=request.query_params.get("academicYearId") or None,
            event_tag=request.query_params.get("eventTag") or None,
            search=request.query_params.get("q") or None,
            date_from=_parse_date(request.query_params.get("dateFrom")),
            date_to=_parse_date(request.query_params.get("dateTo")),
            school_only=request.query_params.get("schoolOnly") == "true",
        )
        total = qs.count()
        offset = (page - 1) * page_size
        albums = list(qs[offset : offset + page_size])
        return Response({
            "albums": [album_payload(a) for a in albums],
            "total": total,
            "page": page,
            "pageSize": page_size,
        })

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        title = request.data.get("title")
        academic_year_id = request.data.get("academicYearId")
        batch_id = request.data.get("batchId")
        if not academic_year_id:
            year = AcademicYear.objects.filter(branch=branch, is_current=True).first()
            if year is None:
                raise ValidationError({"academicYearId": "Academic year is required."})
        else:
            year = AcademicYear.objects.get(pk=academic_year_id, branch=branch)
        batch = None
        if batch_id:
            batch = Batch.objects.get(pk=batch_id, course__department__branch=branch)
        album = album_i.create_album(
            branch=branch,
            academic_year=year,
            title=title,
            user=request.user,
            batch=batch,
            description=request.data.get("description", ""),
            visibility=request.data.get("visibility", "students"),
            event_tag=request.data.get("eventTag", ""),
        )
        return Response(album_payload(album), status=http.HTTP_201_CREATED)


class AdminStorageUsageView(APIView):
    """GET /api/v1/gallery/storage/ — tenant storage quota + gallery stats."""

    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        from apps.organizations.billing.storage_quota import storage_status_payload

        branch = resolve_branch(request)
        return Response(storage_status_payload(branch.tenant))


class AdminAlbumDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, album_id) -> Response:
        branch = resolve_branch(request)
        try:
            album = album_q.get_for_branch(branch.pk, album_id)
        except ObjectDoesNotExist:
            return Response({"error": "Album not found."}, status=http.HTTP_404_NOT_FOUND)
        page = max(int(request.query_params.get("page", 1)), 1)
        page_size = min(int(request.query_params.get("pageSize", 48)), 100)
        images, total = image_q.paginate_for_album(album.pk, page=page, page_size=page_size)
        return Response({
            "album": album_payload(album),
            "images": [image_payload(i) for i in images],
            "total": total,
            "page": page,
            "pageSize": page_size,
        })

    def patch(self, request, album_id) -> Response:
        branch = resolve_branch(request)
        try:
            album = album_q.get_for_branch(branch.pk, album_id)
        except ObjectDoesNotExist:
            return Response({"error": "Album not found."}, status=http.HTTP_404_NOT_FOUND)
        album = album_i.update_album(
            album,
            user=request.user,
            title=request.data.get("title"),
            description=request.data.get("description"),
            visibility=request.data.get("visibility"),
            event_tag=request.data.get("eventTag"),
            sort_order=request.data.get("sortOrder"),
        )
        return Response(album_payload(album))

    def delete(self, request, album_id) -> Response:
        branch = resolve_branch(request)
        try:
            album = album_q.get_for_branch(branch.pk, album_id)
        except ObjectDoesNotExist:
            return Response({"error": "Album not found."}, status=http.HTTP_404_NOT_FOUND)
        album_i.delete_album(album, user=request.user)
        return Response({"success": True})


class AdminAlbumReorderView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, album_id) -> Response:
        branch = resolve_branch(request)
        album = album_q.get_for_branch(branch.pk, album_id)
        image_ids = request.data.get("imageIds") or []
        if not image_ids:
            raise ValidationError({"imageIds": "Provide imageIds in desired order."})
        album_i.reorder_images(album, image_ids, user=request.user)
        return Response({"success": True})


class AdminAlbumCoverView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, album_id) -> Response:
        branch = resolve_branch(request)
        album = album_q.get_for_branch(branch.pk, album_id)
        image_id = request.data.get("imageId")
        if not image_id:
            raise ValidationError({"imageId": "imageId is required."})
        album = album_i.set_cover(album, image_id, user=request.user)
        return Response(album_payload(album))


class AdminImageStagingUploadView(APIView):
    """Direct staging upload for sandbox/dev when presigned PUT is unavailable."""

    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, image_id) -> Response:
        branch = resolve_branch(request)
        album_id = request.data.get("albumId") or request.query_params.get("albumId")
        album = album_q.get_for_branch(branch.pk, album_id)
        image = image_q.get_for_album(album.pk, image_id)
        upload = request.FILES.get("file")
        if upload is None:
            raise ValidationError({"file": "file is required."})
        from apps.gallery.services.storage import get_gallery_storage
        storage = get_gallery_storage()
        if not image.staging_key:
            raise ValidationError({"imageId": "No staging key for this image."})
        content = upload.read()
        validate_upload_meta(
            file_name=upload.name,
            content_type=upload.content_type or "application/octet-stream",
            file_size=len(content),
        )
        storage.upload_file(
            key=image.staging_key,
            content=content,
            content_type=upload.content_type or "application/octet-stream",
        )
        image.file_size = len(content)
        image.original_file_name = upload.name
        image.save(update_fields=["file_size", "original_file_name", "updated_at"])
        return Response({"success": True})


class AdminImagePresignView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        from apps.organizations.billing.storage_quota import storage_warning_snapshot

        branch = resolve_branch(request)
        album_id = request.data.get("albumId")
        files = request.data.get("files") or []
        if not album_id:
            raise ValidationError({"albumId": "albumId is required."})
        if not files:
            raise ValidationError({"files": "Provide at least one file spec."})
        album = album_q.get_for_branch(branch.pk, album_id)
        uploads = image_i.presign_uploads(album=album, files=files, user=request.user)
        return Response({
            "uploads": uploads,
            "storage": storage_warning_snapshot(branch.tenant),
        })


class AdminImageConfirmView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        album_id = request.data.get("albumId")
        image_id = request.data.get("imageId")
        if not album_id or not image_id:
            raise ValidationError({"albumId": "albumId and imageId are required."})
        album = album_q.get_for_branch(branch.pk, album_id)
        from django.conf import settings as dj_settings
        sync = getattr(dj_settings, "CELERY_TASK_ALWAYS_EAGER", False) or request.data.get("sync")
        image = image_i.confirm_upload(
            album=album, image_id=image_id, user=request.user, sync_process=bool(sync),
        )
        return Response(image_payload(image))


class AdminImageBulkDeleteView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        album_id = request.data.get("albumId")
        image_ids = request.data.get("imageIds") or []
        album = album_q.get_for_branch(branch.pk, album_id)
        deleted = image_i.bulk_delete_images(album=album, image_ids=image_ids, user=request.user)
        return Response({"deleted": deleted})


class AdminImageMoveView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        source_id = request.data.get("sourceAlbumId")
        target_id = request.data.get("targetAlbumId")
        image_ids = request.data.get("imageIds") or []
        source = album_q.get_for_branch(branch.pk, source_id)
        target = album_q.get_for_branch(branch.pk, target_id)
        moved = image_i.move_images(
            source_album=source, target_album=target, image_ids=image_ids, user=request.user,
        )
        return Response({"moved": moved})


class AdminImageStatusView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, image_id) -> Response:
        branch = resolve_branch(request)
        album_id = request.query_params.get("albumId")
        if not album_id:
            raise ValidationError({"albumId": "albumId query param is required."})
        album = album_q.get_for_branch(branch.pk, album_id)
        image = image_q.get_for_album(album.pk, image_id)
        return Response(image_payload(image))

    def post(self, request, image_id) -> Response:
        branch = resolve_branch(request)
        album_id = request.data.get("albumId")
        album = album_q.get_for_branch(branch.pk, album_id)
        image_q.get_for_album(album.pk, image_id)
        image = image_i.retry_processing(image_id)
        return Response(image_payload(image))


class FacultyImagePresignView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def post(self, request) -> Response:
        return AdminImagePresignView().post(request)


class FacultyImageConfirmView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def post(self, request) -> Response:
        return AdminImageConfirmView().post(request)


class ReaderAlbumListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        role = request.user.role
        qs = album_q.list_for_branch(branch.pk)
        visible = [a for a in qs if visibility_allows(role, a.visibility)]
        page = max(int(request.query_params.get("page", 1)), 1)
        page_size = min(int(request.query_params.get("pageSize", 24)), 100)
        total = len(visible)
        offset = (page - 1) * page_size
        albums = visible[offset : offset + page_size]
        return Response({
            "albums": [album_payload(a) for a in albums],
            "total": total,
            "page": page,
            "pageSize": page_size,
        })


class ReaderAlbumDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, album_id) -> Response:
        branch = resolve_branch(request)
        try:
            album = album_q.get_for_branch(branch.pk, album_id)
        except ObjectDoesNotExist:
            return Response({"error": "Album not found."}, status=http.HTTP_404_NOT_FOUND)
        if not visibility_allows(request.user.role, album.visibility):
            return Response({"error": "Album not found."}, status=http.HTTP_404_NOT_FOUND)
        page = max(int(request.query_params.get("page", 1)), 1)
        page_size = min(int(request.query_params.get("pageSize", 48)), 100)
        images, total = image_q.paginate_for_album(album.pk, page=page, page_size=page_size, ready_only=True)
        return Response({
            "album": album_payload(album),
            "images": [image_payload(i) for i in images],
            "total": total,
            "page": page,
            "pageSize": page_size,
        })
