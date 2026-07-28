"""Views — report exports + NAAC (admin/super_admin) + catalog/preview/saved filters."""

from django.http import HttpResponse
from django.utils.timezone import now
from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.models.user import Role
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.analytics.enums import ReportStatus
from apps.analytics.enums import ReportType
from apps.analytics.interactors import audit as audit_i
from apps.analytics.interactors import report as report_i
from apps.analytics.permissions import (
    REPORT_DOWNLOADED,
    CanDownloadReport,
    CanRunReport,
    user_can_access_export,
)
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
from apps.core.exceptions import GoneError
from apps.core.exports.catalog import catalog_for_user
from apps.core.exports.filename import build_download_filename
from apps.core.exports.preview import preview_export
from apps.core.exports.registry import get_definition


def _export_not_found():
    return Response({"error": "Report not found."}, status=http.HTTP_404_NOT_FOUND)


def _get_accessible_export(request, export_id):
    """Tenant-scoped fetch + branch/requester gate. Denied → None (caller returns 404)."""
    export = report_q.get_export(request.user.tenant_id, export_id)
    if not export or not user_can_access_export(request.user, export):
        return None
    return export


def _audit_download(request, export) -> None:
    audit_i.record_audit(
        tenant=request.user.tenant,
        actor=request.user,
        action=REPORT_DOWNLOADED,
        entity_type="report_export",
        entity_id=str(export.pk),
        diff={
            "reportType": export.report_type,
            "params": export.params or {},
            "branchId": str(export.branch_id) if export.branch_id else None,
        },
        request=request,
    )


def _download_filename(export) -> str:
    try:
        definition = get_definition(export.report_type)
    except (ImportError, ValueError):
        definition = None
    return build_download_filename(definition, export=export, params=export.params or {})


def _is_file_expired(export) -> bool:
    if export.status == ReportStatus.EXPIRED:
        return True
    if export.expires_at and export.expires_at < now():
        return True
    return False


class ReportCatalogView(APIView):
    """GET → metadata catalog for reports visible to the caller."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        branch = None
        try:
            if getattr(request.user, "role", None) in (Role.ADMIN, Role.SUPER_ADMIN, Role.FACULTY):
                branch = resolve_branch(request)
        except Exception:  # noqa: BLE001
            branch = None
        return Response(catalog_for_user(request.user, branch=branch))


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

        branch = None if data["reportType"] == ReportType.BRANCH_SUMMARY else resolve_branch(
            request, branch_id=data.get("branchId"),
        )
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
        if not CanRunReport().has_permission(request, self):
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
            branch = resolve_branch(request, branch_id=s.validated_data.get("branchId"))
            try:
                export = report_i.generate_report(
                    tenant=request.user.tenant, branch=branch,
                    report_type=report_type, params=s.validated_data["params"],
                    requester=request.user,
                )
            except Exception as exc:
                from rest_framework.exceptions import ValidationError as DRFValidationError
                if isinstance(exc, DRFValidationError):
                    raise
                return Response({"error": str(exc)}, status=http.HTTP_400_BAD_REQUEST)
        return Response({"report": ReportExportSerializer(export).data},
                        status=http.HTTP_201_CREATED)


class ReportDetailView(APIView):
    permission_classes = [IsAuthenticated, CanDownloadReport]

    def get(self, request, export_id):
        export = _get_accessible_export(request, export_id)
        if not export:
            return _export_not_found()
        return Response({"report": ReportExportSerializer(export).data})


class ReportDownloadView(APIView):
    """GET → CSV file for a ready export (inline snapshot or S3-backed)."""

    permission_classes = [IsAuthenticated, CanDownloadReport]

    def get(self, request, export_id):
        export = _get_accessible_export(request, export_id)
        if not export:
            return _export_not_found()
        if _is_file_expired(export):
            raise GoneError("Report file expired — regenerate.")
        if export.status != ReportStatus.READY:
            return Response({"error": "Export is not ready yet."}, status=http.HTTP_409_CONFLICT)

        filename = _download_filename(export)

        if export.file_key:
            from apps.integrations.adapters.s3 import S3NotFoundError, get_s3_adapter

            try:
                content = get_s3_adapter().download(key=export.file_key)
            except S3NotFoundError:
                if export.download_url:
                    _audit_download(request, export)
                    return Response({"downloadUrl": export.download_url})
                return Response({"error": "Export file not found."}, status=http.HTTP_404_NOT_FOUND)
            _audit_download(request, export)
            response = HttpResponse(content, content_type="text/csv")
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        if export.download_url:
            _audit_download(request, export)
            return Response({"downloadUrl": export.download_url})

        rows = (export.snapshot or {}).get("rows", [])
        columns = None
        try:
            definition = get_definition(export.report_type)
            columns = definition.get_columns(export.params or {})
        except (ImportError, ValueError):
            if export.report_type == ReportType.BRANCH_SUMMARY:
                from apps.core.exports.base import Column
                columns = [
                    Column("branch_id", "Branch ID"),
                    Column("branch_name", "Branch Name"),
                    Column("code", "Code"),
                    Column("city", "City"),
                    Column("is_active", "Active"),
                    Column("created_at", "Created At"),
                ]
        content = rows_to_csv_bytes(rows, columns)
        _audit_download(request, export)
        response = HttpResponse(content, content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class ReportRetryView(APIView):
    """POST → re-dispatch a failed / timed-out / expired export."""

    permission_classes = [IsAuthenticated, CanDownloadReport]

    def post(self, request, export_id):
        export = _get_accessible_export(request, export_id)
        if not export:
            return _export_not_found()
        try:
            export = report_i.retry_export(export=export, requester=request.user)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=http.HTTP_409_CONFLICT)
        return Response({"report": ReportExportSerializer(export).data})


class NaacExportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        branch = resolve_branch(request)
        return Response(report_i.naac_export(tenant=request.user.tenant, branch=branch))
