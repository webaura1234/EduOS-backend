"""Self-service export endpoint — faculty's own subject attendance.

Identity scoping (facultyId) is always derived from request.user, never from the
request body, so a faculty member cannot read another faculty's attendance data.
"""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsFaculty, IsStudent
from apps.accounts.models.profile import StudentProfile
from apps.admissions.queries.enrollment import resolve_enrollment_for_profile
from apps.analytics.serializers.report import ReportExportSerializer
from apps.attendance.exports import FacultySubjectAttendanceExport, StudentAttendanceExport
from apps.core.exports.runner import request_export


class FacultySubjectAttendanceExportView(APIView):
    permission_classes = [IsAuthenticated, IsFaculty]

    def post(self, request):
        branch = resolve_branch(request)
        export = request_export(
            FacultySubjectAttendanceExport(),
            tenant=request.user.tenant,
            branch=branch,
            params={
                "facultyId": str(request.user.id),
                "fromDate": request.data.get("fromDate"),
                "toDate": request.data.get("toDate"),
            },
            requested_by=request.user,
        )
        return Response({"report": ReportExportSerializer(export).data}, status=http.HTTP_201_CREATED)


class StudentAttendanceExportView(APIView):
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
            StudentAttendanceExport(),
            tenant=request.user.tenant,
            branch=enrollment.branch,
            params={
                "enrollmentId": str(enrollment.pk),
                "fromDate": request.data.get("fromDate"),
                "toDate": request.data.get("toDate"),
            },
            requested_by=request.user,
        )
        return Response({"report": ReportExportSerializer(export).data}, status=http.HTTP_201_CREATED)
