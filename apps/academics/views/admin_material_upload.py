"""Study material file upload/download.

Upload: admin multipart POST — stores the file via the S3 adapter and creates
the StudyMaterial row in one step (no presign round-trip; files are small).
Download: streams the stored bytes back to any authenticated user of the same
tenant, so materials work in sandbox mode where signed URLs are stubs.
"""

import mimetypes
import uuid

from django.http import HttpResponse
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.interactors.study_materials import material_dict
from apps.academics.queries import admin_extras as extra_q
from apps.academics.queries import structure as struct_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.integrations.adapters.s3 import S3NotFoundError, get_s3_adapter

MAX_STUDY_MATERIAL_BYTES = 25 * 1024 * 1024  # 25 MB


class AdminStudyMaterialUploadView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request)

        upload = request.FILES.get("file")
        if upload is None:
            return Response({"error": "file is required."}, status=status.HTTP_400_BAD_REQUEST)

        batch = struct_q.get_batch(branch.pk, request.data.get("classSectionId"))
        if batch is None:
            return Response({"error": "Class not found."}, status=status.HTTP_404_NOT_FOUND)

        folder = None
        folder_id = request.data.get("folderId")
        if folder_id:
            folder = extra_q.get_folder(branch.pk, folder_id)
            if folder is None or folder.batch_id != batch.pk:
                return Response(
                    {"error": "Folder not found for this class."},
                    status=status.HTTP_404_NOT_FOUND,
                )

        content = upload.read()
        if not content:
            return Response({"error": "File is empty."}, status=status.HTTP_400_BAD_REQUEST)
        if len(content) > MAX_STUDY_MATERIAL_BYTES:
            return Response(
                {"error": "File is too large (max 25 MB)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        file_name = (upload.name or "material")[:255]
        content_type = (
            upload.content_type
            or mimetypes.guess_type(file_name)[0]
            or "application/octet-stream"
        )
        key = f"study-materials/{branch.tenant_id}/{batch.pk}/{uuid.uuid4().hex}-{file_name}"

        adapter = get_s3_adapter()
        adapter.upload(key=key, content=content, content_type=content_type)

        url = adapter.signed_url(key=key)
        # Sandbox signed URLs are stubs the browser cannot fetch; leave url empty so
        # clients fall back to the streaming download endpoint below.
        if "sandbox-s3.local" in url:
            url = ""

        material = extra_q.create_study_material(
            branch=branch,
            batch=batch,
            folder=folder,
            file_name=file_name,
            s3_key=key,
            url=url,
            user=request.user,
        )
        return Response({"material": material_dict(material)}, status=status.HTTP_201_CREATED)


class StudyMaterialDownloadView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, material_id) -> Response:
        material = (
            extra_q.get_study_material(request.user.branch_id, material_id)
            if request.user.branch_id
            else None
        )
        if material is None:
            # Admin/super-admin may live on another branch of the same tenant.
            from apps.academics.models.admin_extras import StudyMaterial

            material = StudyMaterial.objects.filter(
                pk=material_id,
                branch__tenant_id=request.user.tenant_id,
                is_active=True,
            ).first()
        if material is None:
            return Response({"error": "Study material not found."}, status=status.HTTP_404_NOT_FOUND)

        if not material.s3_key:
            return Response(
                {"error": "This material has no stored file."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            content = get_s3_adapter().download(key=material.s3_key)
        except S3NotFoundError:
            return Response({"error": "Stored file not found."}, status=status.HTTP_404_NOT_FOUND)

        content_type = (
            mimetypes.guess_type(material.file_name)[0] or "application/octet-stream"
        )
        response = HttpResponse(content, content_type=content_type)
        response["Content-Disposition"] = f'inline; filename="{material.file_name}"'
        return response
