"""Views — student/parent examination hubs (read-only)."""

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.models.profile import StudentProfile
from apps.accounts.permissions import IsParent, IsStudent
from apps.examinations.interactors import hub as hub_i
from apps.examinations.queries import hub as hub_q
from apps.examinations.serializers.assignment import AssignmentSerializer, SubmissionSerializer
from apps.examinations.serializers.hub import StudentExamHubSerializer, StudentResultsHubSerializer


def _student_profile_or_404(user) -> StudentProfile:
    try:
        return user.student_profile
    except StudentProfile.DoesNotExist:
        raise ValidationError("Student profile not found.")


class StudentExamHubView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        profile = _student_profile_or_404(request.user)
        payload = hub_i.build_exam_hub(profile, tenant=request.user.tenant)
        return Response({"hub": StudentExamHubSerializer(payload).data})


class StudentResultsHubView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        profile = _student_profile_or_404(request.user)
        payload = hub_i.build_results_hub(profile, tenant=request.user.tenant)
        return Response({"results": StudentResultsHubSerializer(payload).data})


class StudentAssignmentsHubView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        profile = _student_profile_or_404(request.user)
        payload = hub_i.build_assignments_hub(profile, branch_id=branch.pk)
        return Response(
            {
                "assignments": AssignmentSerializer(payload["assignments"], many=True).data,
                "submissions": SubmissionSerializer(payload["submissions"], many=True).data,
            }
        )


class ParentChildExamHubView(APIView):
    permission_classes = [IsAuthenticated, IsParent]

    def get(self, request, student_id) -> Response:
        profile = hub_q.student_profile_for_guardian(request.user.pk, student_id)
        if not profile:
            return Response({"error": "Not a linked child."}, status=status.HTTP_403_FORBIDDEN)
        payload = hub_i.build_exam_hub(profile, tenant=request.user.tenant)
        return Response({"hub": StudentExamHubSerializer(payload).data})


class ParentChildResultsHubView(APIView):
    permission_classes = [IsAuthenticated, IsParent]

    def get(self, request, student_id) -> Response:
        profile = hub_q.student_profile_for_guardian(request.user.pk, student_id)
        if not profile:
            return Response({"error": "Not a linked child."}, status=status.HTTP_403_FORBIDDEN)
        payload = hub_i.build_results_hub(profile, tenant=request.user.tenant)
        return Response({"results": StudentResultsHubSerializer(payload).data})


class ParentChildAssignmentsHubView(APIView):
    permission_classes = [IsAuthenticated, IsParent]

    def get(self, request, student_id) -> Response:
        profile = hub_q.student_profile_for_guardian(request.user.pk, student_id)
        if not profile:
            return Response({"error": "Not a linked child."}, status=status.HTTP_403_FORBIDDEN)
        batch = profile.current_batch
        if not batch:
            return Response({"error": "Student has no current batch."}, status=status.HTTP_404_NOT_FOUND)
        branch = batch.course.department.branch
        payload = hub_i.build_assignments_hub(profile, branch_id=branch.pk)
        return Response(
            {
                "assignments": AssignmentSerializer(payload["assignments"], many=True).data,
                "submissions": SubmissionSerializer(payload["submissions"], many=True).data,
            }
        )
