"""Student analysis API views."""

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.student_analysis.services.report_service import get_student_report


class StudentReportView(APIView):
    """GET student analysis report by roll number."""

    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, roll_number: str) -> Response:
        roll_number = (roll_number or "").strip()
        if not roll_number:
            return Response(
                {"error": "Roll number is required."},
                status=http.HTTP_400_BAD_REQUEST,
            )

        try:
            report = get_student_report(roll_number, tenant_id=request.user.tenant_id)
        except ObjectDoesNotExist:
            return Response(
                {"error": f"No student found for roll number: {roll_number}"},
                status=http.HTTP_404_NOT_FOUND,
            )

        request_tenant_id = getattr(request.user, "tenant_id", None)
        student_tenant_id = report.get("student", {}).get("tenantId")
        if request_tenant_id and student_tenant_id != str(request_tenant_id):
            return Response(
                {"error": f"No student found for roll number: {roll_number}"},
                status=http.HTTP_404_NOT_FOUND,
            )

        return Response(report)
