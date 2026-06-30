"""
MFA views — second-factor OTP verification.
"""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.interactors.mfa import verify_mfa_otp
from apps.accounts.serializers.auth import MFAVerifySerializer
from apps.accounts.views.auth import _get_client_ip


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
            device_info=request.META.get("HTTP_USER_AGENT", ""),
            ip_address=_get_client_ip(request),
        )

        return Response(result, status=status.HTTP_200_OK)
