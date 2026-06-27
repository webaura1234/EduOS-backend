"""Views — assignments (faculty/admin) and submissions (student/faculty)."""

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.models.profile import StudentProfile
from apps.accounts.permissions import IsStudent
from apps.examinations.interactors import assignment as asg_i
from apps.examinations.permissions import IsFacultyOrAdmin
from apps.examinations.queries import assignment as asg_q
from apps.examinations.serializers.assignment import (
    AssignmentSerializer,
    CreateAssignmentSerializer,
    FacultyCreateAssignmentSerializer,
    GradeSubmissionSerializer,
    SubmissionSerializer,
    SubmitAssignmentSerializer,
)


class AssignmentListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        batch_id = request.query_params.get("classSectionId") or request.query_params.get("batchId")
        subject_id = request.query_params.get("subjectId")
        payload = asg_i.list_assignments_data(
            branch_id=branch.pk,
            batch_id=batch_id,
            subject_id=subject_id,
        )
        return Response(
            {
                "assignments": AssignmentSerializer(payload["assignments"], many=True).data,
                "submissions": SubmissionSerializer(payload["submissions"], many=True).data,
            }
        )

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        serializer = CreateAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        assignment = asg_i.create_assignment(
            branch_id=branch.pk,
            title=data["title"],
            description=data.get("description", ""),
            batch_id=data["classSectionId"],
            subject_id=data["subjectId"],
            due_at_raw=data["dueAt"],
            max_marks=data["maxMarks"],
            actor=request.user,
            academic_period_id=data.get("academicPeriodId"),
        )
        return Response({"assignment": AssignmentSerializer(assignment).data}, status=status.HTTP_201_CREATED)


class FacultyTeachingAssignmentsView(APIView):
    """Faculty portal — my class vs other classes assignment scoping."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        payload = asg_i.list_faculty_teaching_assignments_data(
            branch_id=branch.pk,
            faculty_id=request.user.pk,
        )
        return Response(payload)

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        serializer = FacultyCreateAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        assignment = asg_i.create_faculty_teaching_assignment(
            branch_id=branch.pk,
            faculty_id=request.user.pk,
            title=data["title"],
            description=data.get("description", ""),
            batch_id=data["classSectionId"],
            subject_id=data["subjectId"],
            due_at_raw=data["dueAt"],
            max_marks=data.get("maxMarks", 25),
            actor=request.user,
            academic_period_id=data.get("academicPeriodId"),
        )
        return Response({"assignment": AssignmentSerializer(assignment).data}, status=status.HTTP_201_CREATED)


class AssignmentSubmitView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def post(self, request, assignment_id) -> Response:
        branch = resolve_branch(request)
        assignment = asg_q.get_assignment(branch.pk, assignment_id)
        if not assignment:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            student_profile = request.user.student_profile
        except StudentProfile.DoesNotExist:
            raise ValidationError("Student profile not found.")

        serializer = SubmitAssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payload = asg_i.submit_assignment(
            assignment,
            student_profile=student_profile,
            file_name=data["fileName"],
            file_content=data["fileContent"],
            actor=request.user,
        )
        return Response({"submission": SubmissionSerializer(payload).data, "fileKey": payload.get("fileKey", "")})


class SubmissionGradeView(APIView):
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def patch(self, request, submission_id) -> Response:
        branch = resolve_branch(request)
        submission = asg_q.get_submission(branch.pk, submission_id)
        if not submission:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = GradeSubmissionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        updated = asg_i.grade_submission(
            submission,
            graded_marks_raw=serializer.validated_data["gradedMarks"],
            actor=request.user,
        )
        return Response({"submission": SubmissionSerializer(updated).data})
