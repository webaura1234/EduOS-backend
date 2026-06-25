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
    platform_login,
    refresh_tokens,
    switch_linked_account,
)
from apps.accounts.queries.user import list_linked_accounts
from apps.accounts.serializers.auth import (
    DisambiguateLoginSerializer,
    LoginSerializer,
    LogoutSerializer,
    PlatformLoginSerializer,
    RefreshSerializer,
    SwitchLinkedSerializer,
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
        from apps.organizations.branding import branch_theme, tenant_theme

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
        # Resolved branding for the user's branch (override → tenant fallback) so the
        # authed app can re-theme per branch without an extra round-trip.
        if user.branch_id:
            theme = branch_theme(user.branch)
        elif user.tenant_id:
            theme = tenant_theme(user.tenant)
        else:
            theme = None
        return Response({**dto.to_dict(), "theme": theme}, status=status.HTTP_200_OK)


def _auth_user_payload(user) -> dict:
    """AuthUser-shaped dict the frontend consumes directly (F-223 account switch)."""
    tenant = user.tenant
    return {
        "id": str(user.id),
        "name": user.full_name,
        "role": user.role,
        "phone": user.phone,
        "custom_login_id": user.custom_login_id,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "tenant_subdomain": tenant.subdomain if tenant else None,
        "linked_user_group_id": (
            str(user.linked_user_group_id) if user.linked_user_group_id else None
        ),
        "institution_type": tenant.institution_type if tenant else None,
    }


class PlatformLoginView(APIView):
    """
    POST /api/v1/auth/platform/login/

    Authenticate a tenant-less platform owner (phone + password). Public endpoint.
    """
    permission_classes = [AllowAny]

    def post(self, request) -> Response[LoginResponseDTO]:
        serializer = PlatformLoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result: LoginResponseDTO = platform_login(
            identifier=serializer.validated_data["identifier"],
            password=serializer.validated_data["password"],
            device_info=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=_get_client_ip(request),
        )
        return Response(result, status=status.HTTP_200_OK)


class LinkedAccountsView(APIView):
    """
    GET /api/v1/auth/linked-accounts/

    The other accounts (same person, multiple roles) linked to the caller (F-223).
    """
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        rows = list_linked_accounts(request.user)
        data = [
            {
                "userId": str(u.id),
                "role": u.role,
                "name": u.full_name,
                "label": u.get_role_display(),
            }
            for u in rows
        ]
        return Response(data, status=status.HTTP_200_OK)


class SwitchLinkedAccountView(APIView):
    """
    POST /api/v1/auth/switch-linked/

    Switch to a linked account; re-verifies the target account's password and issues a
    fresh token pair for it (F-223).
    """
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        serializer = SwitchLinkedSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target, dto = switch_linked_account(
            current_user=request.user,
            target_user_id=str(serializer.validated_data["target_user_id"]),
            password=serializer.validated_data["password"],
            device_info=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=_get_client_ip(request),
        )
        return Response(
            {"user": _auth_user_payload(target), "access": dto.access, "refresh": dto.refresh},
            status=status.HTTP_200_OK,
        )


class StepUpVerifyView(APIView):
    """
    POST /api/v1/auth/step-up/

    Re-verify the current user's password before a sensitive action (F-262).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        password = (request.data.get("password") or "").strip()
        if not password:
            return Response({"error": "Password is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not request.user.check_password(password):
            return Response({"error": "Incorrect password."}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"verified": True}, status=status.HTTP_200_OK)
