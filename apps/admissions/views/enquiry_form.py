"""Views — configurable enquiry form (admin management + public shareable form)."""

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.admissions.enums import EnquirySource
from apps.admissions.interactors import enquiry as enquiry_i
from apps.admissions.interactors import enquiry_form as form_i
from apps.admissions.serializers.enquiry_form import (
    SaveEnquiryFormSerializer,
    enquiry_form_dict,
    public_enquiry_form_dict,
)
from apps.organizations.queries.branch import list_branches
from apps.organizations.queries.tenant import get_active_tenant_by_subdomain


class EnquiryFormView(APIView):
    """
    GET /api/v1/admissions/enquiry-form/   → the branch's form definition
    PUT /api/v1/admissions/enquiry-form/   → replace title/description/fields/isPublic
    """
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        form = form_i.get_or_create_form(branch)
        return Response(enquiry_form_dict(form))

    def put(self, request) -> Response:
        branch = resolve_branch(request)
        serializer = SaveEnquiryFormSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        form = form_i.save_form(
            branch,
            title=data["title"],
            description=data["description"],
            is_public=data["isPublic"],
            fields=data["fields"],
        )
        return Response(enquiry_form_dict(form))


def _public_branch(subdomain: str):
    """Resolve (branch, tenant) for a public subdomain, or (None, None)."""
    tenant = get_active_tenant_by_subdomain((subdomain or "").strip().lower())
    if tenant is None:
        return None, None
    branch = list_branches(tenant.id).first()
    return branch, tenant


class PublicEnquiryFormView(APIView):
    """GET /api/v1/admissions/public/enquiry-form/?subdomain=<sub> → form schema (no auth)."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request) -> Response:
        branch, tenant = _public_branch(request.query_params.get("subdomain", ""))
        if branch is None:
            return Response({"error": "Institution not found."}, status=status.HTTP_404_NOT_FOUND)
        form = form_i.get_or_create_form(branch)
        if not form.is_public:
            return Response(
                {"error": "This enquiry form is not currently accepting submissions."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(
            public_enquiry_form_dict(form, institution_name=tenant.name, subdomain=tenant.subdomain)
        )


class PublicEnquirySubmitView(APIView):
    """POST /api/v1/admissions/public/enquiry/ → create an enquiry from the public form (no auth)."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "public_enquiry"

    def post(self, request) -> Response:
        data = request.data or {}

        # Honeypot: real users never fill the hidden field; bots do. Pretend success.
        if str(data.get("_hp", "")).strip():
            return Response({"ok": True}, status=status.HTTP_201_CREATED)

        branch, _tenant = _public_branch(data.get("subdomain", ""))
        if branch is None:
            return Response({"error": "Institution not found."}, status=status.HTTP_404_NOT_FOUND)

        form = form_i.get_or_create_form(branch)
        if not form.is_public:
            return Response(
                {"error": "This enquiry form is not currently accepting submissions."},
                status=status.HTTP_403_FORBIDDEN,
            )

        applicant_name = str(data.get("applicantName", "")).strip()
        phone = str(data.get("phone", "")).strip()
        if not applicant_name:
            return Response({"applicantName": "Your name is required."}, status=status.HTTP_400_BAD_REQUEST)
        if not phone:
            return Response({"phone": "A contact number is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Raises DRF ValidationError (→ 400) on any bad custom answer.
        custom_fields = form_i.validate_submission(form, data.get("customFields") or {})

        enquiry_i.capture_enquiry(
            branch=branch,
            source=EnquirySource.ONLINE,
            applicant_name=applicant_name,
            phone=phone,
            email=str(data.get("email", "")).strip(),
            notes=str(data.get("notes", "")).strip(),
            custom_fields=custom_fields,
            is_public_submission=True,
        )
        return Response({"ok": True}, status=status.HTTP_201_CREATED)
