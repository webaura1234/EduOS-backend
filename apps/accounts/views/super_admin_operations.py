"""Super-admin operations overview."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.interactors import super_admin_operations as ops_i
from apps.accounts.permissions import IsSuperAdmin


class SuperAdminOperationsOverviewView(APIView):
    """GET → branch people counts + totals."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request) -> Response:
        return Response(ops_i.operations_overview(request.user.tenant))
