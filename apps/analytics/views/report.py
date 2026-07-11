"""Views — report exports + NAAC (admin/super_admin) + catalog/preview/saved filters."""

from django.http import HttpResponse
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.models.user import Role
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.analytics.enums import ReportStatus
from apps.analytics.enums import ReportType
from apps.analytics.interactors import report as report_i
from apps.analytics.queries import report as report_q
from apps.analytics.queries import saved_filter as sf_q
from apps.analytics.serializers.report import (
    CreateReportSerializer,
    CreateSavedFilterSerializer,
    PreviewReportSerializer,
    ReportExportSerializer,
    SavedReportFilterSerializer,
)
from apps.analytics.tasks import rows_to_csv_bytes
from apps.core.exports.catalog import catalog_for_user
from apps.core.exports.preview import preview_export
from apps.core.exports.registry import get_definition


class ReportCatalogView(APIView):
    """GET → metadata catalog for reports visible to the caller."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"reports": catalog_for_user(request.user)})


class ReportPreviewView(APIView):
    """POST → paginated preview for reports with supports_preview=True."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        s = PreviewReportSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        try:
            definition = get_definition(data["reportType"])
        except ValueError:
            return Response({"error": "Report not found."}, status=http.HTTP_404_NOT_FOUND)

        if definition.allowed_roles and request.user.role not in definition.allowed_roles:
            return Response({"error": "Forbidden."}, status=http.HTTP_403_FORBIDDEN)
        if not definition.supports_preview:
            return Response({"error": "This report does not support preview."}, status=http.HTTP_400_BAD_REQUEST)

        branch = None if data["reportType"] == ReportType.BRANCH_SUMMARY else resolve_branch(request)
        try:
            result = preview_export(
                definition,
                tenant=request.user.tenant,
                branch=branch,
                params=data.get("params") or {},
                page=data.get("page") or 1,
                page_size=data.get("pageSize") or 50,
                search=data.get("search") or "",
                sort_key=data.get("sortKey") or "",
                sort_dir=data.get("sortDir") or "asc",
            )
        except Exception as exc:
            return Response({"error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)
        return Response({"preview": result})


class SavedReportFiltersView(APIView):
    """GET → list saved filters; POST → create; DELETE via detail URL."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        report_type = request.query_params.get("reportType")
        rows = sf_q.list_saved_filters(
            request.user.tenant_id, request.user.pk, report_type=report_type,
        )
        return Response({"filters": SavedReportFilterSerializer(rows, many=True).data})

    def post(self, request):
        s = CreateSavedFilterSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        try:
            get_definition(data["reportType"])
        except ValueError:
            return Response({"error": "Report not found."}, status=http.HTTP_404_NOT_FOUND)
        row = sf_q.create_saved_filter(
            tenant=request.user.tenant,
            user=request.user,
            report_type=data["reportType"],
            name=data["name"],
            params=data.get("params") or {},
        )
        return Response(
            {"filter": SavedReportFilterSerializer(row).data},
            status=http.HTTP_201_CREATED,
        )


class SavedReportFilterDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, filter_id):
        if not sf_q.delete_saved_filter(request.user.tenant_id, request.user.pk, filter_id):
            return Response({"error": "Not found."}, status=http.HTTP_404_NOT_FOUND)
        return Response(status=http.HTTP_204_NO_CONTENT)


class ReportExportsView(APIView):
    """GET → recent exports; POST → create export."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        limit = min(int(request.query_params.get("limit", 50)), 100)
        report_type = request.query_params.get("reportType")
        requested_by_me = request.query_params.get("requestedBy") == "me"

        if request.user.role in (Role.ADMIN, Role.SUPER_ADMIN) and not requested_by_me:
            if request.user.role == Role.SUPER_ADMIN and not request.query_params.get("branch"):
                rows = report_q.list_exports(
                    request.user.tenant_id, report_type=report_type,
                )
            else:
                branch = resolve_branch(request)
                rows = report_q.list_exports(
                    request.user.tenant_id, branch_id=branch.pk, report_type=report_type,
                )
        else:
            rows = report_q.list_exports(
                request.user.tenant_id,
                requested_by_id=request.user.pk,
                report_type=report_type,
            )
        return Response({"reports": ReportExportSerializer(rows[:limit], many=True).data})

    def post(self, request):
        if request.user.role not in (Role.ADMIN, Role.SUPER_ADMIN):
            return Response({"error": "Forbidden."}, status=http.HTTP_403_FORBIDDEN)
        s = CreateReportSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        report_type = s.validated_data["reportType"]
        if report_type == ReportType.BRANCH_SUMMARY:
            if request.user.role != Role.SUPER_ADMIN:
                return Response(
                    {"error": "Only super admins can export branch summaries."},
                    status=http.HTTP_403_FORBIDDEN,
                )
            export = report_i.generate_report(
                tenant=request.user.tenant, branch=None,
                report_type=report_type, params=s.validated_data["params"],
                requester=request.user,
            )
        else:
            branch = resolve_branch(request)
            export = report_i.generate_report(
                tenant=request.user.tenant, branch=branch,
                report_type=report_type, params=s.validated_data["params"],
                requester=request.user,
            )
        return Response({"report": ReportExportSerializer(export).data},
                        status=http.HTTP_201_CREATED)


class ReportDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, export_id):
        export = report_q.get_export(request.user.tenant_id, export_id)
        if not export:
            return Response({"error": "Report not found."}, status=http.HTTP_404_NOT_FOUND)
        if request.user.role not in (Role.ADMIN, Role.SUPER_ADMIN):
            if export.requested_by_id != request.user.pk:
                return Response({"error": "Forbidden."}, status=http.HTTP_403_FORBIDDEN)
        return Response({"report": ReportExportSerializer(export).data})


class ReportDownloadView(APIView):
    """GET → CSV file for a ready export (inline snapshot or S3-backed)."""

    permission_classes = [IsAuthenticated]

    def get(self, request, export_id):
        export = report_q.get_export(request.user.tenant_id, export_id)
        if not export:
            return Response({"error": "Report not found."}, status=http.HTTP_404_NOT_FOUND)
        if request.user.role not in (Role.ADMIN, Role.SUPER_ADMIN):
            if export.requested_by_id != request.user.pk:
                return Response({"error": "Forbidden."}, status=http.HTTP_403_FORBIDDEN)
        if export.status != ReportStatus.READY:
            return Response({"error": "Export is not ready yet."}, status=http.HTTP_409_CONFLICT)

        filename = f"{export.report_type}-{export.pk}.csv"

        if export.file_key:
            from apps.integrations.adapters.s3 import S3NotFoundError, get_s3_adapter

            try:
                content = get_s3_adapter().download(key=export.file_key)
            except S3NotFoundError:
                if export.download_url:
                    return Response({"downloadUrl": export.download_url})
                return Response({"error": "Export file not found."}, status=http.HTTP_404_NOT_FOUND)
            response = HttpResponse(content, content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        if export.download_url:
            return Response({"downloadUrl": export.download_url})

        rows = (export.snapshot or {}).get("rows", [])
        content = rows_to_csv_bytes(rows)
        response = HttpResponse(content, content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class NaacExportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = resolve_branch(request)
        return Response(report_i.naac_export(tenant=request.user.tenant, branch=branch))
