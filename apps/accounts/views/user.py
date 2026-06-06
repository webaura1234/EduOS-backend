from __future__ import annotations

"""
User-management views (admin actions on users).

  - AdminResetPasswordView → admin manually resets a user's password (EC-AUTH-21).
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.interactors.password import admin_reset_password
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.accounts.serializers.password import AdminResetPasswordSerializer


class AdminResetPasswordView(APIView):
    """
    POST /api/v1/auth/users/<user_id>/reset-password/

    Admin sets a temporary password for a user; the user is forced to change it on
    next login (EC-AUTH-21). Returns the temp password so the admin can relay it.
    Requires admin / super_admin.
    """
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, user_id) -> Response:
        serializer = AdminResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        temp = admin_reset_password(
            admin=request.user,
            target_user_id=str(user_id),
            temp_password=serializer.validated_data.get("temp_password") or None,
        )
        return Response(
            {"detail": "Password reset. Share the temporary password with the user.",
             "temp_password": temp},
            status=status.HTTP_200_OK,
        )
