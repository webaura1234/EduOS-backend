from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from apps.organizations.branding import tenant_theme
from apps.organizations.queries.tenant import (
    get_active_tenant_by_subdomain,
    get_tenant_id_labels,
)


class TenantConfigView(APIView):
    """
    GET /api/v1/organizations/tenant-config/

    Resolve a tenant by subdomain and return its settings and configurations
    required for the login screen and frontend client context.
    Public endpoint.
    """
    permission_classes = [AllowAny]

    def get(self, request) -> Response:
        subdomain = request.query_params.get("subdomain")
        if not subdomain:
            return Response(
                {"error": "subdomain query parameter is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        tenant = get_active_tenant_by_subdomain(subdomain)
        if tenant is None:
            return Response(
                {"error": f"Tenant with subdomain '{subdomain}' not found or inactive"},
                status=status.HTTP_404_NOT_FOUND,
            )

        student_id_label, faculty_id_label = get_tenant_id_labels(tenant)

        theme = tenant_theme(tenant)

        return Response(
            {
                "tenant_id": str(tenant.id),
                "institution_name": tenant.name,
                "institution_type": tenant.institution_type,
                # logo_url kept for back-compat; theme.logoUrl is the canonical source.
                "logo_url": theme["logoUrl"],
                "theme": theme,
                "subdomain": tenant.subdomain,
                "student_id_label": student_id_label,
                "faculty_id_label": faculty_id_label,
            },
            status=status.HTTP_200_OK,
        )
