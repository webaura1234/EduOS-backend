from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import AllowAny

from apps.organizations.models.tenant import Tenant, TenantSettings


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

        try:
            tenant = Tenant.objects.get(subdomain__iexact=subdomain.strip(), status="active")
        except Tenant.DoesNotExist:
            return Response(
                {"error": f"Tenant with subdomain '{subdomain}' not found or inactive"},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Retrieve configurable labels or fall back to defaults
        try:
            settings = tenant.tenant_settings
            student_id_label = settings.student_id_label
            faculty_id_label = settings.faculty_id_label
        except TenantSettings.DoesNotExist:
            student_id_label = "Roll Number"
            faculty_id_label = "Employee ID"

        logo_url = None
        if tenant.logo_s3_key:
            logo_url = tenant.logo_s3_key

        return Response(
            {
                "tenant_id": str(tenant.id),
                "institution_name": tenant.name,
                "institution_type": tenant.institution_type,
                "logo_url": logo_url,
                "subdomain": tenant.subdomain,
                "student_id_label": student_id_label,
                "faculty_id_label": faculty_id_label,
            },
            status=status.HTTP_200_OK,
        )
