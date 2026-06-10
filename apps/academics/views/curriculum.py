"""Views — Subject, BatchSubject, BatchFaculty."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.interactors import curriculum as curr_i
from apps.academics.interactors.curriculum import SubjectHasMarksError
from apps.academics.permissions import IsAdminOrSuperAdmin
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import structure as struct_q
from apps.academics.scoping import resolve_branch
from apps.academics.serializers.curriculum import (
    BatchFacultySerializer,
    BatchSubjectSerializer,
    CreateBatchFacultySerializer,
    CreateBatchSubjectSerializer,
    CreateSubjectSerializer,
    SubjectSerializer,
    UpdateBatchFacultySerializer,
    UpdateBatchSubjectSerializer,
    UpdateSubjectSerializer,
)
from apps.academics.views.structure import _map_fields


class SubjectListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        subjects = curr_q.list_subjects(branch.pk, course_id=request.query_params.get("courseId"))
        return Response({"subjects": SubjectSerializer(subjects, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        serializer = CreateSubjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        course = struct_q.get_course(branch.pk, data["courseId"])
        if not course:
            return Response({"error": "Course not found."}, status=status.HTTP_404_NOT_FOUND)
        subject = curr_i.create_subject(
            request.user.tenant, course,
            name=data["name"], code=data.get("code", ""),
            subject_type=data.get("subjectType", "theory"),
            max_marks=data.get("maxMarks", 100), pass_marks=data.get("passMarks", 35),
            credits=data.get("credits"), is_elective=data.get("isElective", False),
            user=request.user,
        )
        return Response({"subject": SubjectSerializer(subject).data}, status=status.HTTP_201_CREATED)


class SubjectDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, subject_id) -> Response:
        branch = resolve_branch(request)
        subject = curr_q.get_subject(branch.pk, subject_id)
        if not subject:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateSubjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = _map_fields(data, {
            "name": "name", "code": "code", "subjectType": "subject_type",
            "maxMarks": "max_marks", "passMarks": "pass_marks",
            "credits": "credits", "isElective": "is_elective", "version": "version",
        })
        subject = curr_i.update_subject(request.user.tenant, subject, fields=fields, user=request.user)
        return Response({"subject": SubjectSerializer(subject).data})

    def delete(self, request, subject_id) -> Response:
        branch = resolve_branch(request)
        subject = curr_q.get_subject(branch.pk, subject_id)
        if not subject:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        try:
            result = curr_i.delete_subject(subject, user=request.user)
        except SubjectHasMarksError:
            return Response({"hasMarks": True}, status=status.HTTP_409_CONFLICT)
        return Response(result)


class BatchSubjectListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        items = curr_q.list_batch_subjects(
            branch.pk,
            batch_id=request.query_params.get("batchId"),
            academic_period_id=request.query_params.get("academicPeriodId"),
        )
        return Response({"batchSubjects": BatchSubjectSerializer(items, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        serializer = CreateBatchSubjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        batch = struct_q.get_batch(branch.pk, data["batchId"])
        subject = curr_q.get_subject(branch.pk, data["subjectId"])
        if not batch or not subject:
            return Response({"error": "Batch or subject not found."}, status=status.HTTP_404_NOT_FOUND)
        period = cal_q.get_period(batch.academic_year_id, data["academicPeriodId"])
        if not period:
            return Response({"error": "Academic period not found."}, status=status.HTTP_404_NOT_FOUND)
        bs = curr_i.create_batch_subject(
            batch, subject, period, is_required=data.get("isRequired", True), user=request.user,
        )
        return Response({"batchSubject": BatchSubjectSerializer(bs).data}, status=status.HTTP_201_CREATED)


class BatchSubjectDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, batch_subject_id) -> Response:
        branch = resolve_branch(request)
        bs = curr_q.get_batch_subject(branch.pk, batch_subject_id)
        if not bs:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateBatchSubjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = _map_fields(data, {"isRequired": "is_required", "version": "version"})
        bs = curr_i.update_batch_subject(bs, fields=fields, user=request.user)
        return Response({"batchSubject": BatchSubjectSerializer(bs).data})

    def delete(self, request, batch_subject_id) -> Response:
        branch = resolve_branch(request)
        bs = curr_q.get_batch_subject(branch.pk, batch_subject_id)
        if not bs:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        curr_i.delete_batch_subject(bs, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class BatchFacultyListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        items = curr_q.list_batch_faculty(
            branch.pk, batch_subject_id=request.query_params.get("batchSubjectId")
        )
        return Response({"batchFaculty": BatchFacultySerializer(items, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        serializer = CreateBatchFacultySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        bs = curr_q.get_batch_subject(branch.pk, data["batchSubjectId"])
        if not bs:
            return Response({"error": "Batch subject not found."}, status=status.HTTP_404_NOT_FOUND)
        assignment = curr_i.create_batch_faculty(
            request.user.tenant_id, bs,
            faculty_id=data["facultyId"], role=data.get("role", "primary"),
            assigned_at=data["assignedAt"], ended_at=data.get("endedAt"),
            user=request.user,
        )
        return Response({"batchFaculty": BatchFacultySerializer(assignment).data}, status=status.HTTP_201_CREATED)


class BatchFacultyDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, assignment_id) -> Response:
        branch = resolve_branch(request)
        assignment = curr_q.get_batch_faculty(branch.pk, assignment_id)
        if not assignment:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateBatchFacultySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = _map_fields(data, {"role": "role", "endedAt": "ended_at", "version": "version"})
        assignment = curr_i.update_batch_faculty(assignment, fields=fields, user=request.user)
        return Response({"batchFaculty": BatchFacultySerializer(assignment).data})

    def delete(self, request, assignment_id) -> Response:
        branch = resolve_branch(request)
        assignment = curr_q.get_batch_faculty(branch.pk, assignment_id)
        if not assignment:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        curr_i.delete_batch_faculty(assignment, user=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)
