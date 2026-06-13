"""Views — report exports + NAAC (admin/super_admin)."""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.analytics.interactors import report as report_i
from apps.analytics.queries import report as report_q
from apps.analytics.serializers.report import CreateReportSerializer, ReportExportSerializer


class ReportCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        branch = resolve_branch(request)
        s = CreateReportSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        export = report_i.generate_report(
            tenant=request.user.tenant, branch=branch,
            report_type=s.validated_data["reportType"], params=s.validated_data["params"],
            requester=request.user,
        )
        return Response({"report": ReportExportSerializer(export).data},
                        status=http.HTTP_201_CREATED)


class ReportDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, export_id):
        export = report_q.get_export(request.user.tenant_id, export_id)
        if not export:
            return Response({"error": "Report not found."}, status=http.HTTP_404_NOT_FOUND)
        return Response({"report": ReportExportSerializer(export).data})


class NaacExportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = resolve_branch(request)
        return Response(report_i.naac_export(tenant=request.user.tenant, branch=branch))
