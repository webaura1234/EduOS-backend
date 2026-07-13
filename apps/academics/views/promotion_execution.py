"""Views — Promotion execution (Phase 3)."""

from django.http import HttpResponse
from rest_framework import status
from rest_framework.negotiation import BaseContentNegotiation
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

from apps.academics.exceptions import PromotionExecutionInProgressError
from apps.academics.interactors import promotion_execution as exec_i
from apps.academics.permissions import IsAdminOrSuperAdmin
from apps.academics.scoping import resolve_branch
from apps.academics.serializers.promotion_execution import PromotionExecuteSerializer


class _IgnoreFormatQueryParamNegotiation(BaseContentNegotiation):
    """DRF treats ?format= as renderer selection; this view uses it for export type."""

    def select_renderer(self, request, renderers, format_suffix=None):
        return renderers[0], renderers[0].media_type


def _execution_conflict_response(exc: PromotionExecutionInProgressError) -> Response:
    detail = exc.detail if isinstance(exc.detail, dict) else {}
    return Response(
        {
            "detail": detail.get("detail", PromotionExecutionInProgressError.default_detail),
            "code": detail.get("code", PromotionExecutionInProgressError.default_code),
            "runningSessionId": detail.get("runningSessionId"),
            **({"runId": detail["runId"]} if detail.get("runId") else {}),
        },
        status=status.HTTP_409_CONFLICT,
    )


class PromotionExecuteDryRunView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(exec_i.get_dry_run(branch_id=branch.pk, session_id=session_id))


class PromotionExecuteView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        serializer = PromotionExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            return Response(
                exec_i.start_execution(
                    branch_id=branch.pk,
                    session_id=session_id,
                    confirmation_phrase_input=serializer.validated_data["confirmationPhrase"],
                    confirm_token=serializer.validated_data.get("confirmToken"),
                    user=request.user,
                    request=request,
                )
            )
        except PromotionExecutionInProgressError as exc:
            return _execution_conflict_response(exc)


class PromotionExecuteStatusView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(exec_i.get_execution_status(branch_id=branch.pk, session_id=session_id))


class PromotionExecuteReportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        return Response(exec_i.get_execution_report(branch_id=branch.pk, session_id=session_id))


class PromotionExecuteReportDownloadView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    renderer_classes = [JSONRenderer]
    content_negotiation_class = _IgnoreFormatQueryParamNegotiation

    def get(self, request, session_id):
        from apps.core.exports.pdf import PdfRenderError

        branch = resolve_branch(request)
        fmt = request.query_params.get("format", "csv")
        if fmt == "pdf":
            try:
                content = exec_i.export_report_pdf(branch_id=branch.pk, session_id=session_id)
            except PdfRenderError:
                return Response(
                    {
                        "error": "pdf_unavailable",
                        "message": "PDF rendering is unavailable. Download CSV instead.",
                        "fallbackFormat": "csv",
                    },
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = 'attachment; filename="promotion-report.pdf"'
            return response
        content = exec_i.export_report_csv(branch_id=branch.pk, session_id=session_id)
        response = HttpResponse(content, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="promotion-report.csv"'
        return response


class PromotionExecuteResumeView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, session_id) -> Response:
        branch = resolve_branch(request)
        try:
            return Response(
                exec_i.resume_execution(
                    branch_id=branch.pk,
                    session_id=session_id,
                    user=request.user,
                )
            )
        except PromotionExecutionInProgressError as exc:
            return _execution_conflict_response(exc)
