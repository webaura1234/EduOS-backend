"""Self-service export endpoint — student's own fee statement.

Identity scoping (studentUserId) is always derived from request.user.
"""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models.profile import StudentProfile
from apps.accounts.permissions import IsStudent
from apps.analytics.serializers.report import ReportExportSerializer
from apps.core.exports.runner import request_export
from apps.fees.exports import StudentFeeStatementExport


class StudentFeeStatementExportView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request):
        try:
            profile = request.user.student_profile
        except StudentProfile.DoesNotExist:
            return Response({"error": "Student profile not found."}, status=http.HTTP_404_NOT_FOUND)

        export = request_export(
            StudentFeeStatementExport(),
            tenant=request.user.tenant,
            branch=request.user.branch,
            params={"studentUserId": str(request.user.id)},
            requested_by=request.user,
        )
        return Response({"report": ReportExportSerializer(export).data}, status=http.HTTP_201_CREATED)
