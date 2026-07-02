"""Self-service export endpoints — faculty's own class results, student's own exam results.

Identity scoping (facultyId / enrollmentId) is always derived from request.user.
"""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.models.profile import StudentProfile
from apps.accounts.permissions import IsFaculty, IsStudent
from apps.admissions.queries.enrollment import resolve_enrollment_for_profile
from apps.analytics.serializers.report import ReportExportSerializer
from apps.core.exports.runner import request_export
from apps.examinations.exports import FacultyClassResultsExport, StudentExamResultsExport


class FacultyClassResultsExportView(APIView):
    permission_classes = [IsAuthenticated, IsFaculty]

    def post(self, request):
        branch = resolve_branch(request)
        export = request_export(
            FacultyClassResultsExport(),
            tenant=request.user.tenant,
            branch=branch,
            params={
                "facultyId": str(request.user.id),
                "examId": request.data.get("examId"),
            },
            requested_by=request.user,
        )
        return Response({"report": ReportExportSerializer(export).data}, status=http.HTTP_201_CREATED)


class StudentExamResultsExportView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request):
        try:
            profile = request.user.student_profile
        except StudentProfile.DoesNotExist:
            return Response({"error": "Student profile not found."}, status=http.HTTP_404_NOT_FOUND)

        enrollment = resolve_enrollment_for_profile(profile)
        if enrollment is None:
            return Response({"error": "No active enrollment found."}, status=http.HTTP_404_NOT_FOUND)

        export = request_export(
            StudentExamResultsExport(),
            tenant=request.user.tenant,
            branch=enrollment.branch,
            params={"enrollmentId": str(enrollment.pk)},
            requested_by=request.user,
        )
        return Response({"report": ReportExportSerializer(export).data}, status=http.HTTP_201_CREATED)
