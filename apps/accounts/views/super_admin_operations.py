"""Super-admin operations overview."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.interactors import super_admin_operations as ops_i
from apps.accounts.permissions import IsSuperAdmin
from apps.core.cache import cached_response, get_or_compute


class SuperAdminOperationsOverviewView(APIView):
    """GET → branch people counts + totals (memoised briefly; X-Cache-Age reported)."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request) -> Response:
        tenant = request.user.tenant
        data, computed_at = get_or_compute(
            f"ops-overview:{tenant.pk}",
            lambda: ops_i.operations_overview(tenant),
        )
        return cached_response(data, computed_at)
