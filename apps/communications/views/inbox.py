"""Notification inbox views."""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.communications.queries import inbox as inbox_q
from apps.communications.serializers.inbox import NotificationSerializer


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        category = request.query_params.get("category") or None
        try:
            limit = min(int(request.query_params.get("limit", 50)), 100)
        except ValueError:
            limit = 50
        try:
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except ValueError:
            offset = 0

        rows = inbox_q.list_for_recipient(
            request.user.pk, category=category, limit=limit, offset=offset,
        )
        return Response({
            "notifications": NotificationSerializer(rows, many=True).data,
            "unreadCount": inbox_q.unread_count(request.user.pk),
        })


class NotificationUnreadCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        return Response({"unreadCount": inbox_q.unread_count(request.user.pk)})


class NotificationMarkReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, notification_id) -> Response:
        row = inbox_q.get_for_recipient(request.user.pk, notification_id)
        if not row:
            return Response({"error": "Notification not found."}, status=http.HTTP_404_NOT_FOUND)
        row = inbox_q.mark_read(row, user=request.user)
        return Response({"notification": NotificationSerializer(row).data})


class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request) -> Response:
        count = inbox_q.mark_all_read(request.user.pk, user=request.user)
        return Response({"success": True, "markedCount": count})


class NotificationBranchRecentView(APIView):
    """Admin dashboard widget — recent notifications sent in this branch."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        rows = inbox_q.branch_recent(branch.pk, limit=20)
        return Response({
            "notifications": NotificationSerializer(rows, many=True).data,
        })
