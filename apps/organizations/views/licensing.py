"""Tenant-scoped licensing APIs for school dashboards.

Super Admin sees the whole tenant; Branch Admin additionally gets counts for
their own branch. Both are read-only — all licensing writes happen on the
platform-owner endpoints.
"""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models.user import Role
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.organizations.queries import licensing as q
from apps.organizations.serializers.licensing import payment_dict


class LicensingSummaryView(APIView):
    """GET /api/v1/organizations/licensing/summary/"""

    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        tenant = request.user.tenant
        if tenant is None:
            return Response({"error": "No tenant."}, status=http.HTTP_400_BAD_REQUEST)

        branch_id = request.user.branch_id if request.user.role == Role.ADMIN else None
        data = q.tenant_scoped_summary(tenant, branch_id=branch_id)

        # Super Admin also sees payment history (read-only).
        if request.user.role == Role.SUPER_ADMIN:
            from apps.organizations.models import LicensePayment

            payments = (
                LicensePayment.objects.select_related("recorded_by")
                .filter(tenant=tenant, is_active=True)
                .order_by("-paid_at", "-created_at")[:50]
            )
            data["payments"] = [payment_dict(p) for p in payments]
        return Response(data)


class LicensingStudentsView(APIView):
    """GET /api/v1/organizations/licensing/students/?status=unlicensed"""

    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        tenant = request.user.tenant
        if tenant is None:
            return Response({"error": "No tenant."}, status=http.HTTP_400_BAD_REQUEST)

        branch_id = request.user.branch_id if request.user.role == Role.ADMIN else None
        students = q.tenant_students(
            tenant,
            status=request.query_params.get("status"),
            branch_id=branch_id,
        )
        return Response({"students": students})
