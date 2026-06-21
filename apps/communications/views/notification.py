"""Views — per-user notification preferences (F-179). Any authenticated user manages own."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.communications.queries import notification as pref_q


def _payload(user, pref) -> dict:
    """Shape the frontend consumes: { userId, channels: {in_app, sms, email} }."""
    return {
        "userId": str(user.id),
        "channels": {"in_app": pref.in_app, "sms": pref.sms, "email": pref.email},
    }


class NotificationPreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        pref = pref_q.get_or_create_preference(request.user)
        return Response(_payload(request.user, pref))

    def patch(self, request) -> Response:
        pref = pref_q.get_or_create_preference(request.user)
        # Accept any subset of {in_app, sms, email} booleans.
        fields = {k: bool(v) for k, v in request.data.items() if k in {"in_app", "sms", "email"}}
        pref = pref_q.update_preference(pref, fields, user=request.user)
        return Response(_payload(request.user, pref))
