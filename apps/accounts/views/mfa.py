"""
MFA views — second-factor OTP verification.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.interactors.mfa import verify_mfa_otp, request_otp_login
from apps.accounts.serializers.auth import MFAVerifySerializer, OtpLoginRequestSerializer
from apps.accounts.views.auth import _device_info_from_request, _get_client_ip


class MFAVerifyView(APIView):
    """
    POST /api/v1/auth/mfa/verify/

    Complete a login that required MFA.  Submit the mfa_session_token received
    from the login response along with the 6-digit OTP sent to the user's email.

    On success, returns the same token pair as a normal login response.
    Public endpoint. Throttled at the auth scope (10 req/min).
    """
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request) -> Response:
        serializer = MFAVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        result = verify_mfa_otp(
            mfa_session_token=data["mfa_session_token"],
            otp=data["otp"],
            device_info=_device_info_from_request(request),
            ip_address=_get_client_ip(request),
        )

        return Response(result, status=status.HTTP_200_OK)


class OtpLoginRequestView(APIView):
    """
    POST /api/v1/auth/otp-login/request/

    Passwordless login for admin, super_admin, and platform_owner.
    Sends a 6-digit OTP to the user's registered email.
    """
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request) -> Response:
        serializer = OtpLoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        tenant_id = data.get("tenant_id")
        result = request_otp_login(
            phone=data["phone"],
            tenant_id=str(tenant_id) if tenant_id else None,
            user_id=str(data["user_id"]) if data.get("user_id") else None,
            ip_address=_get_client_ip(request),
        )
        return Response(result.to_dict(), status=status.HTTP_200_OK)
