"""
Auth views — Login, Refresh, Logout, Me.

Views are thin: validate input via serializer → call interactor → return response.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.interactors.auth import login, logout, refresh_tokens
from apps.accounts.serializers.auth import (
    LoginSerializer,
    LogoutSerializer,
    MeSerializer,
    RefreshSerializer,
    TokenPairSerializer,
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

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = login(
            identifier=data["identifier"],
            password=data["password"],
            role=data["role"],
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

    def post(self, request):
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = refresh_tokens(
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

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        logout(refresh_token_str=serializer.validated_data["refresh"])

        return Response({"detail": "Logged out successfully."}, status=status.HTTP_200_OK)


class MeView(APIView):
    """
    GET /api/v1/auth/me/

    Return the currently authenticated user's profile.
    Requires authentication.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        serializer = MeSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
