from __future__ import annotations

"""
Invite views — CreateInvite (admin) and AcceptInvite (new user).
"""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.dtos import InviteAcceptedDTO, InviteCreatedDTO
from apps.accounts.interactors.invite import accept_invite, create_and_send_invite
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.accounts.serializers.invite import (
    AcceptInviteSerializer,
    CreateInviteSerializer,
)


def _get_client_ip(request) -> str:
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


class CreateInviteView(APIView):
    """
    POST /api/v1/auth/invite/create/

    Admin creates a new user and sends them an invite SMS.
    Requires authentication + admin/super_admin role.
    """
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response[InviteCreatedDTO]:
        serializer = CreateInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = create_and_send_invite(
            created_by=request.user,
            role=data["role"],
            first_name=data["first_name"],
            last_name=data.get("last_name", ""),
            phone=data.get("phone") or None,
            custom_login_id=data.get("custom_login_id") or None,
            email=data.get("email"),
            tenant_id=request.user.tenant_id,
            branch_id=data.get("branch_id"),
        )

        return Response(result, status=status.HTTP_201_CREATED)


class AcceptInviteView(APIView):
    """
    POST /api/v1/auth/invite/accept/

    New user sets their first password using an invite token.
    Public endpoint — no authentication required (they don't have credentials yet).
    Returns a token pair so the user is immediately logged in.
    """
    permission_classes = [AllowAny]

    def post(self, request) -> Response[InviteAcceptedDTO]:
        serializer = AcceptInviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = accept_invite(
            token_uuid=data["token"],
            new_password=data["new_password"],
            device_info=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=_get_client_ip(request),
        )

        return Response(result, status=status.HTTP_200_OK)
