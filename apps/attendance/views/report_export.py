"""Attendance export endpoints — async CSV generation via the shared ReportExport pipeline.

These are distinct from views/attendance.py's report views: those return live JSON for
on-screen viewing; these create a ReportExport job the client polls and downloads as CSV.
"""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.analytics.enums import ReportType
from apps.analytics.interactors import report as report_i
from apps.analytics.serializers.report import ReportExportSerializer


class AttendanceMonthlyExportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        branch = resolve_branch(request)
        export = report_i.generate_report(
            tenant=request.user.tenant, branch=branch,
            report_type=ReportType.ATTENDANCE_MONTHLY,
            params={
                "year": request.data.get("year"),
                "month": request.data.get("month"),
                "batchId": request.data.get("batchId"),
            },
            requester=request.user,
        )
        return Response({"report": ReportExportSerializer(export).data}, status=http.HTTP_201_CREATED)


class AttendanceShortageExportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        branch = resolve_branch(request)
        export = report_i.generate_report(
            tenant=request.user.tenant, branch=branch,
            report_type=ReportType.ATTENDANCE_SHORTAGE,
            params={
                "threshold": request.data.get("threshold"),
                "batchId": request.data.get("batchId"),
                "fromDate": request.data.get("fromDate"),
                "toDate": request.data.get("toDate"),
            },
            requester=request.user,
        )
        return Response({"report": ReportExportSerializer(export).data}, status=http.HTTP_201_CREATED)


class AttendanceRankingExportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        branch = resolve_branch(request)
        export = report_i.generate_report(
            tenant=request.user.tenant, branch=branch,
            report_type=ReportType.ATTENDANCE_RANKING,
            params={
                "batchId": request.data.get("batchId"),
                "fromDate": request.data.get("fromDate"),
                "toDate": request.data.get("toDate"),
            },
            requester=request.user,
        )
        return Response({"report": ReportExportSerializer(export).data}, status=http.HTTP_201_CREATED)


class AttendanceDetentionExportView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        branch = resolve_branch(request)
        export = report_i.generate_report(
            tenant=request.user.tenant, branch=branch,
            report_type=ReportType.ATTENDANCE_DETENTION,
            params={
                "batchId": request.data.get("batchId"),
                "fromDate": request.data.get("fromDate"),
                "toDate": request.data.get("toDate"),
            },
            requester=request.user,
        )
        return Response({"report": ReportExportSerializer(export).data}, status=http.HTTP_201_CREATED)
