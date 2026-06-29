"""Super-admin exam results comparison (F-039)."""

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsSuperAdmin
from apps.analytics.interactors import results_comparison as results_i


class SuperAdminResultsComparisonView(APIView):
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request) -> Response:
        branch_id = request.query_params.get("branchId") or None
        exam_id = request.query_params.get("examId") or None
        data = results_i.super_admin_results_comparison(
            request.user.tenant,
            branch_id=branch_id,
            exam_id=exam_id,
        )
        resp = Response({**data, "lastUpdated": timezone.now().isoformat()})
        resp["X-Cache-Age"] = "0"
        return resp
