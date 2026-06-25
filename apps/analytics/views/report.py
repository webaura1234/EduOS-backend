"""Views — report exports + NAAC (admin/super_admin)."""

from django.http import HttpResponse
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.analytics.enums import ReportStatus
from apps.analytics.interactors import report as report_i
from apps.analytics.queries import report as report_q
from apps.analytics.serializers.report import CreateReportSerializer, ReportExportSerializer
from apps.analytics.tasks import rows_to_csv_bytes


class ReportExportsView(APIView):
    """GET → recent exports; POST → create export."""

    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = resolve_branch(request)
        limit = min(int(request.query_params.get("limit", 50)), 100)
        rows = report_q.list_exports(request.user.tenant_id, branch_id=branch.pk)[:limit]
        return Response({"reports": ReportExportSerializer(rows, many=True).data})

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


class ReportDownloadView(APIView):
    """GET → CSV file for a ready export (inline snapshot or S3-backed)."""

    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, export_id):
        export = report_q.get_export(request.user.tenant_id, export_id)
        if not export:
            return Response({"error": "Report not found."}, status=http.HTTP_404_NOT_FOUND)
        if export.status != ReportStatus.READY:
            return Response({"error": "Export is not ready yet."}, status=http.HTTP_409_CONFLICT)

        if export.download_url:
            return Response({"downloadUrl": export.download_url})

        rows = (export.snapshot or {}).get("rows", [])
        content = rows_to_csv_bytes(rows)
        filename = f"{export.report_type}-{export.pk}.csv"
        response = HttpResponse(content, content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class NaacExportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = resolve_branch(request)
        return Response(report_i.naac_export(tenant=request.user.tenant, branch=branch))
