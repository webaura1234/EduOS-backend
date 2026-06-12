"""Views — Funnel Analytics (F-078)."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.admissions.queries import enquiry as enquiry_q


class FunnelAnalyticsView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        counts = enquiry_q.funnel_counts(branch.pk)
        return Response(counts)
