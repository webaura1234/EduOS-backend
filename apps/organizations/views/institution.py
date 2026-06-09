"""
Institution-settings view (super-admin) — GET / PATCH / go-live.

Maps Tenant fields to the frontend `TenantInstitutionSettings` shape and enforces:
  - institution type is immutable after go-live,
  - parent-portal toggle applies only to colleges.
All DB access lives in apps.organizations.queries.institution.
"""

import re

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsSuperAdmin
from apps.organizations.queries import institution as inst_q
from apps.organizations.serializers.institution import (
    GoLiveSerializer,
    UpdateInstitutionSettingsSerializer,
    institution_settings_dict,
)

_SUBDOMAIN_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$")


class InstitutionSettingsView(APIView):
    """GET / PATCH / POST on /api/v1/organizations/institution-settings/ — super-admin only."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request) -> Response:
        tenant = inst_q.get_tenant(request.user.tenant_id)
        if tenant is None:
            return Response({"error": "Institution not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(institution_settings_dict(tenant))

    def patch(self, request) -> Response:
        tenant = inst_q.get_tenant(request.user.tenant_id)
        if tenant is None:
            return Response({"error": "Institution not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = UpdateInstitutionSettingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        next_type = data.get("institutionType", tenant.institution_type)

        # Rule: type is immutable once the institution has gone live.
        if (
            tenant.activated_at is not None
            and "institutionType" in data
            and next_type != tenant.institution_type
        ):
            return Response(
                {"error": "Institution type cannot be changed after go-live."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Rule: parent-portal toggle applies only to colleges.
        if "parentPortalEnabled" in data and next_type != "college":
            return Response(
                {"error": "Parent portal access applies only to college institutions."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        fields: dict = {}
        if "institutionName" in data:
            fields["name"] = data["institutionName"]
        if "institutionType" in data:
            fields["institution_type"] = data["institutionType"]
        if "logoUrl" in data:
            fields["logo_s3_key"] = (data["logoUrl"] or "").strip()
        if "parentPortalEnabled" in data:
            fields["parent_access_enabled"] = data["parentPortalEnabled"]
        if "address" in data:
            addr = data["address"]
            fields.update({
                "address_line1": addr.get("line1", ""),
                "address_line2": addr.get("line2", ""),
                "city": addr.get("city", ""),
                "state": addr.get("state", ""),
                "postal_code": addr.get("pincode", ""),
            })

        tenant = inst_q.update_tenant_fields(tenant, fields)
        return Response(institution_settings_dict(tenant))

    def post(self, request) -> Response:
        tenant = inst_q.get_tenant(request.user.tenant_id)
        if tenant is None:
            return Response({"error": "Institution not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = GoLiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenant = inst_q.set_go_live(tenant, live=serializer.validated_data["action"] == "go_live")
        return Response(institution_settings_dict(tenant))


class SubdomainCheckView(APIView):
    """
    GET /api/v1/organizations/subdomain-check/?q=<subdomain>
        → { "available": bool, "valid": bool }

    Used during tenant onboarding / settings to validate a desired subdomain.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request) -> Response:
        q = (request.query_params.get("q") or "").strip().lower()
        if not q:
            return Response({"error": "q query parameter is required"}, status=status.HTTP_400_BAD_REQUEST)

        valid = bool(_SUBDOMAIN_RE.match(q))
        available = valid and not inst_q.subdomain_taken(q)
        return Response({"available": available, "valid": valid})
