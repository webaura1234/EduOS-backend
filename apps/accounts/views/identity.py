"""
Identity-change views — phone number and email address updates.

All four endpoints require authentication. Callers should obtain step-up
approval via POST /api/v1/auth/step-up/ before hitting initiate.

  POST /api/v1/auth/change-phone/initiate/  → send OTP to new phone
  POST /api/v1/auth/change-phone/confirm/   → verify OTP + update phone
  POST /api/v1/auth/change-email/initiate/  → send OTP to new email
  POST /api/v1/auth/change-email/confirm/   → verify OTP + update email
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.dtos import MessageDTO
from apps.accounts.interactors.identity import (
    confirm_email_change,
    confirm_phone_change,
    initiate_email_change,
    initiate_phone_change,
)


# ─── Phone ────────────────────────────────────────────────────────────────────

class ChangeMobileInitiateView(APIView):
    """
    POST /api/v1/auth/change-phone/initiate/
    body: { new_phone: string }

    Sends a 6-digit OTP to the new phone number.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        new_phone = (request.data.get("new_phone") or "").strip()
        if not new_phone:
            return Response(
                {"detail": "new_phone is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        initiate_phone_change(request.user, new_phone)

        return Response(
            MessageDTO(detail="A verification code has been sent to your new phone number."),
            status=status.HTTP_200_OK,
        )


class ChangeMobileConfirmView(APIView):
    """
    POST /api/v1/auth/change-phone/confirm/
    body: { otp: string }

    Verifies the OTP and updates the user's phone number.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        otp = (request.data.get("otp") or "").strip()
        if not otp:
            return Response(
                {"detail": "otp is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        confirm_phone_change(request.user, otp)

        return Response(
            MessageDTO(detail="Phone number updated successfully."),
            status=status.HTTP_200_OK,
        )


# ─── Email ────────────────────────────────────────────────────────────────────

class ChangeEmailInitiateView(APIView):
    """
    POST /api/v1/auth/change-email/initiate/
    body: { new_email: string }

    Sends a 6-digit OTP to the new email address.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        new_email = (request.data.get("new_email") or "").strip()
        if not new_email:
            return Response(
                {"detail": "new_email is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        initiate_email_change(request.user, new_email)

        return Response(
            MessageDTO(detail="A verification code has been sent to your new email address."),
            status=status.HTTP_200_OK,
        )


class ChangeEmailConfirmView(APIView):
    """
    POST /api/v1/auth/change-email/confirm/
    body: { otp: string }

    Verifies the OTP and updates the user's email address.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        otp = (request.data.get("otp") or "").strip()
        if not otp:
            return Response(
                {"detail": "otp is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        confirm_email_change(request.user, otp)

        return Response(
            MessageDTO(detail="Email address updated successfully."),
            status=status.HTTP_200_OK,
        )
