"""
Session management views.

  GET    /api/v1/auth/sessions/         → list the user's active sessions (refresh tokens)
  DELETE /api/v1/auth/sessions/{id}/    → remotely revoke a specific session
"""

from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import NotFound
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models.token import RefreshToken
from apps.accounts.queries.session import revoke_refresh_token_session


class SessionsView(APIView):
    """List all active sessions for the current user."""

    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        tokens = (
            RefreshToken.objects.filter(
                user=request.user,
                is_revoked=False,
            )
            .filter(expires_at__gt=timezone.now())
            .order_by("-created_at")
        )

        sessions = [
            {
                "id": str(t.id),
                "device_info": t.device_info or "Unknown device",
                "ip_address": t.ip_address,
                "created_at": t.created_at.isoformat(),
                "expires_at": t.expires_at.isoformat(),
            }
            for t in tokens
        ]

        return Response({"sessions": sessions}, status=status.HTTP_200_OK)


class SessionDetailView(APIView):
    """Remotely revoke a single session by its refresh-token ID."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, session_id) -> Response:
        try:
            token = RefreshToken.objects.get(id=session_id, user=request.user)
        except RefreshToken.DoesNotExist:
            raise NotFound("Session not found.")

        if token.is_revoked:
            return Response(
                {"detail": "Session is already revoked."},
                status=status.HTTP_200_OK,
            )

        revoke_refresh_token_session(token)

        return Response(
            {"detail": "Session revoked successfully."},
            status=status.HTTP_200_OK,
        )
