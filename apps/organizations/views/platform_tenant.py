"""
Platform-owner tenant-management views — list/create, detail, status actions.

Platform-owner only. Thin views: validate → interactor/queries → presenter.
"""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsPlatformOwner
from apps.organizations.interactors import platform_tenant as interactor
from apps.organizations.queries import platform_tenant as q
from apps.organizations.serializers.platform_tenant import (
    CreatePlatformTenantSerializer,
    TenantStatusActionSerializer,
    platform_stats_from_summaries,
    tenant_summary,
)


class PlatformTenantListCreateView(APIView):
    """
    GET  /api/v1/organizations/platform/tenants/   → list + filterOptions + stats
    POST /api/v1/organizations/platform/tenants/   → { tenant } (201)
    """
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request) -> Response:
        p = request.query_params
        tenants = q.list_tenants(
            q=p.get("q"),
            plan=p.get("plan", "all"),
            institution_type=p.get("type", "all"),
            city=p.get("city", "all"),
            status=p.get("status", "all"),
        )
        summaries = [tenant_summary(t) for t in tenants]
        return Response({
            "tenants": summaries,
            "filterOptions": {
                "cities": q.distinct_cities(),
                "plans": ["starter", "growth", "enterprise"],
                "institutionTypes": ["school", "college"],
                "statuses": ["active", "inactive", "pending"],
            },
            "stats": q.status_counts(),
            "platformStats": platform_stats_from_summaries(summaries),
        })

    def post(self, request) -> Response:
        serializer = CreatePlatformTenantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            tenant = interactor.create_tenant(serializer.validated_data, user=request.user)
        except DjangoValidationError as exc:
            return Response({"error": "; ".join(exc.messages)}, status=http.HTTP_400_BAD_REQUEST)
        return Response({"tenant": tenant_summary(tenant)}, status=http.HTTP_201_CREATED)


class PlatformTenantDetailView(APIView):
    """GET /api/v1/organizations/platform/tenants/<tenant_id>/ → { tenant }."""
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def get(self, request, tenant_id) -> Response:
        tenant = q.get_tenant(tenant_id)
        if tenant is None:
            return Response({"error": "Tenant not found"}, status=http.HTTP_404_NOT_FOUND)
        return Response({"tenant": tenant_summary(tenant)})


class PlatformTenantActionsView(APIView):
    """
    PATCH /api/v1/organizations/platform/tenants/actions/
        { "tenantId": "...", "action": "activate" | "deactivate" }
    Deactivation terminates all active sessions for the tenant (EC-TEN-04).
    """
    permission_classes = [IsAuthenticated, IsPlatformOwner]

    def patch(self, request) -> Response:
        serializer = TenantStatusActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            tenant, terminated, message = interactor.change_status(
                str(data["tenantId"]), data["action"], user=request.user
            )
        except DjangoValidationError as exc:
            return Response({"error": "; ".join(exc.messages)}, status=http.HTTP_400_BAD_REQUEST)
        return Response({
            "tenant": tenant_summary(tenant),
            "sessionsTerminated": terminated,
            "message": message,
        })
