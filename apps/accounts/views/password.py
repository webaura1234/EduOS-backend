from __future__ import annotations

"""
Password views — ForceChangePassword, OTPRequest, OTPVerify.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.dtos import MessageDTO
from apps.accounts.interactors.password import (
    force_change_password,
    list_reset_accounts,
    request_otp_reset,
    verify_otp_and_reset,
)
from apps.accounts.serializers.password import (
    ForceChangePasswordSerializer,
    OTPRequestSerializer,
    OTPVerifySerializer,
    ResetAccountsSerializer,
)


class ForceChangePasswordView(APIView):
    """
    POST /api/v1/auth/password/change/

    Mandatory first-login password change.
    Requires authentication. Works even when must_change_password=True.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response[MessageDTO]:
        serializer = ForceChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        force_change_password(
            user=request.user,
            current_password=data["current_password"],
            new_password=data["new_password"],
        )

        return Response(
            MessageDTO(detail="Password changed successfully. Please log in again."),
            status=status.HTTP_200_OK,
        )


class OTPRequestView(APIView):
    """
    POST /api/v1/auth/password/reset/request/

    Send an OTP to the phone for password reset.
    Public endpoint. Always returns 200 (don't reveal if phone exists).
    Throttled at 10 requests/minute.
    """
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request) -> Response[MessageDTO]:
        serializer = OTPRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        account_id = data.get("account_id")
        request_otp_reset(
            phone=data["phone"],
            tenant_id=str(data["tenant_id"]),
            account_id=str(account_id) if account_id else None,
        )

        return Response(
            MessageDTO(detail="If a matching account was found, an OTP has been sent."),
            status=status.HTTP_200_OK,
        )


class ResetAccountsView(APIView):
    """
    POST /api/v1/auth/password/reset/accounts/

    Return the accounts registered to a phone so the user can pick which to reset
    when the phone is shared (EC-AUTH-12 / EC-AUTH-20). Public endpoint.
    """
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request) -> Response:
        serializer = ResetAccountsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        accounts = list_reset_accounts(
            phone=data["phone"], tenant_id=str(data["tenant_id"])
        )
        return Response({"accounts": accounts}, status=status.HTTP_200_OK)


class OTPVerifyView(APIView):
    """
    POST /api/v1/auth/password/reset/verify/

    Verify OTP and set a new password.
    Public endpoint. Throttled at 10 requests/minute.
    """
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request) -> Response[MessageDTO]:
        serializer = OTPVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        verify_otp_and_reset(
            phone=data["phone"],
            otp=data["otp"],
            new_password=data["new_password"],
            tenant_id=str(data["tenant_id"]),
        )

        return Response(
            MessageDTO(detail="Password reset successful. Please log in with your new password."),
            status=status.HTTP_200_OK,
        )
