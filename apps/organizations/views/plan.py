"""
Plan view (super-admin) — GET the institution's current plan + usage.
"""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsSuperAdmin
from apps.organizations.queries import plan as plan_q
from apps.organizations.serializers.plan import plan_data_dict


class PlanView(APIView):
    """GET /api/v1/organizations/plan/ — current subscription for the caller's tenant."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request) -> Response:
        subscription = plan_q.get_subscription(request.user.tenant_id)
        return Response(plan_data_dict(subscription))
