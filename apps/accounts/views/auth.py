from __future__ import annotations

"""
Auth views — Login, Refresh, Logout, Me.

Views are thin: validate input via serializer → call interactor → return response.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.dtos import (
    LoginResponseDTO,
    MessageDTO,
    TokenPairDTO,
    UserProfileDTO,
)
from apps.accounts.interactors.auth import (
    disambiguate_login,
    login,
    logout,
    refresh_tokens,
)
from apps.accounts.serializers.auth import (
    DisambiguateLoginSerializer,
    LoginSerializer,
    LogoutSerializer,
    RefreshSerializer,
)


def _get_client_ip(request) -> str:
    """Extract client IP from request, accounting for proxies."""
    x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if x_forwarded_for:
        return x_forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


class LoginView(APIView):
    """
    POST /api/v1/auth/login/

    Authenticate and return an access + refresh token pair.
    Public endpoint — no authentication required.
    Throttled at 10 requests/minute (auth scope).
    """
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request) -> Response[LoginResponseDTO]:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result: LoginResponseDTO = login(
            identifier=data["identifier"],
            password=data["password"],
            role=data["role"],
            tenant_id=str(data["tenant_id"]),
            device_info=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=_get_client_ip(request),
        )

        return Response(result, status=status.HTTP_200_OK)


class LoginDisambiguateView(APIView):
    """
    POST /api/v1/auth/login/disambiguate/

    Universal login: identifier + password (no role). Returns either a token pair
    (single match) or a role picker (phone shared by admin + parent — EC-AUTH-11).
    Public endpoint. Throttled at the auth scope.
    """
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request) -> Response:
        serializer = DisambiguateLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = disambiguate_login(
            identifier=data["identifier"],
            password=data["password"],
            tenant_id=str(data["tenant_id"]),
            device_info=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=_get_client_ip(request),
        )
        return Response(result, status=status.HTTP_200_OK)


class RefreshView(APIView):
    """
    POST /api/v1/auth/refresh/

    Exchange a valid refresh token for a new access + refresh token pair.
    Old refresh token is revoked (token rotation).
    Public endpoint — no authentication required.
    """
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request) -> Response[TokenPairDTO]:
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result: TokenPairDTO = refresh_tokens(
            refresh_token_str=serializer.validated_data["refresh"],
            device_info=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=_get_client_ip(request),
        )

        return Response(result, status=status.HTTP_200_OK)


class LogoutView(APIView):
    """
    POST /api/v1/auth/logout/

    Revoke the provided refresh token. Idempotent.
    Requires authentication.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response[MessageDTO]:
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        logout(refresh_token_str=serializer.validated_data["refresh"])

        return Response(
            MessageDTO(detail="Logged out successfully."), status=status.HTTP_200_OK
        )


class MeView(APIView):
    """
    GET /api/v1/auth/me/

    Return the currently authenticated user's profile.
    Requires authentication.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response[UserProfileDTO]:
        user = request.user
        dto = UserProfileDTO(
            id=user.id,
            role=user.role,
            full_name=user.full_name,
            email=user.email,
            phone=user.phone,
            tenant_id=user.tenant_id,
            branch_id=user.branch_id,
            must_change_password=user.must_change_password,
            date_joined=user.date_joined,
        )
        return Response(dto, status=status.HTTP_200_OK)
