"""Views — role dashboards (read aggregates, live-computed with cache-age header)."""

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin, IsSuperAdmin
from apps.analytics.interactors import dashboard as dash_i


def _with_cache_meta(data: dict) -> Response:
    """OD-1 — live compute; stamp freshness so the UI can show 'last updated' (EC-CACHE-01)."""
    resp = Response({**data, "lastUpdated": timezone.now().isoformat()})
    resp["X-Cache-Age"] = "0"
    return resp


class AdminDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = resolve_branch(request)
        return _with_cache_meta(dash_i.admin_dashboard(branch, request.user.tenant))


class CollectionDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = resolve_branch(request)
        return _with_cache_meta(dash_i.collection_dashboard(branch))


class SuperAdminDashboardView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request):
        return _with_cache_meta(dash_i.super_admin_dashboard(request.user.tenant))


class StudentDashboardView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from rest_framework.exceptions import PermissionDenied
        if request.user.role != "student":
            raise PermissionDenied("Only student accounts can read this dashboard.")
        return _with_cache_meta(dash_i.student_dashboard(request.user))
