"""Avatar upload endpoints for the authenticated user."""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.services.avatar import (
    avatar_object_key,
    avatar_url_for_user,
    validate_avatar_upload,
)
from apps.integrations.adapters.s3 import get_s3_adapter


class AvatarPresignView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        user = request.user
        content_type = (request.data.get("contentType") or "").strip()
        file_size = int(request.data.get("fileSize") or 0)
        err = validate_avatar_upload(content_type=content_type, file_size=file_size)
        if err:
            return Response({"error": err}, status=http.HTTP_400_BAD_REQUEST)
        if not user.tenant_id:
            return Response({"error": "Tenant context required."}, status=http.HTTP_400_BAD_REQUEST)

        key = avatar_object_key(tenant_id=user.tenant_id, user_id=user.pk)
        upload_url = get_s3_adapter().presigned_upload_url(key=key, content_type=content_type)
        return Response({"uploadUrl": upload_url, "key": key})


class AvatarConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        user = request.user
        key = (request.data.get("key") or "").strip()
        expected = avatar_object_key(tenant_id=user.tenant_id, user_id=user.pk) if user.tenant_id else ""
        if not key or key != expected:
            return Response({"error": "Invalid avatar key."}, status=http.HTTP_400_BAD_REQUEST)

        user.avatar_s3_key = key
        user.save(update_fields=["avatar_s3_key"])
        return Response({"avatarUrl": avatar_url_for_user(user)})


class AvatarDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request) -> Response:
        user = request.user
        key = user.avatar_s3_key
        if key:
            get_s3_adapter().delete(key=key)
        user.avatar_s3_key = ""
        user.save(update_fields=["avatar_s3_key"])
        return Response({"avatarUrl": None})
