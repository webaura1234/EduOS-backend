"""Views — grade scales, exams, and schedule slots."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.academics.views.structure import _map_fields
from apps.examinations.interactors import exam as exam_i
from apps.examinations.permissions import IsAdminOrSuperAdmin
from apps.examinations.queries import exam as exam_q
from apps.examinations.serializers.exam import (
    CreateExamSerializer,
    CreateGradeScaleSerializer,
    CreateScheduleSlotSerializer,
    ExamScheduleSlotSerializer,
    ExamSerializer,
    GradeScaleSerializer,
    UpdateExamSerializer,
    UpdateGradeScaleSerializer,
    UpdateScheduleSlotSerializer,
)


class GradeScaleListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        course_id = request.query_params.get("courseId")
        scales = exam_q.list_grade_scales(branch.pk, course_id=course_id)
        return Response({"gradeScales": GradeScaleSerializer(scales, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        serializer = CreateGradeScaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        scale = exam_i.create_grade_scale(
            branch.pk,
            course_id=data["courseId"],
            name=data["name"],
            bands=data["bands"],
            grace_marks_max=data.get("graceMarksMax", 0),
            is_default=data.get("isDefault", False),
            tenant=request.user.tenant,
            user=request.user,
        )
        return Response({"gradeScale": GradeScaleSerializer(scale).data}, status=status.HTTP_201_CREATED)


class GradeScaleDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, scale_id) -> Response:
        branch = resolve_branch(request)
        scale = exam_q.get_grade_scale(branch.pk, scale_id)
        if not scale:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateGradeScaleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = _map_fields(serializer.validated_data, {
            "name": "name",
            "bands": "bands",
            "graceMarksMax": "grace_marks_max",
            "isDefault": "is_default",
            "version": "version",
        })
        scale = exam_i.update_grade_scale(scale, fields=fields, tenant=request.user.tenant, user=request.user)
        return Response({"gradeScale": GradeScaleSerializer(scale).data})


class ExamListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        period_id = request.query_params.get("academicPeriodId")
        exams = exam_q.list_exams(branch.pk, academic_period_id=period_id)
        return Response({"exams": ExamSerializer(exams, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        serializer = CreateExamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        exam = exam_i.create_exam(
            branch.pk,
            academic_period_id=data["academicPeriodId"],
            name=data["name"],
            exam_type=data.get("examType"),
            exam_fee_paise=data.get("examFeePaise", 0),
            marks_deadline=data.get("marksDeadline"),
            user=request.user,
        )
        return Response({"exam": ExamSerializer(exam).data}, status=status.HTTP_201_CREATED)


class ExamDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"exam": ExamSerializer(exam).data})

    def patch(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateExamSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = _map_fields(serializer.validated_data, {
            "name": "name",
            "examType": "exam_type",
            "academicPeriodId": "academic_period_id",
            "examFeePaise": "exam_fee_paise",
            "marksDeadline": "marks_deadline",
            "version": "version",
        })
        exam = exam_i.update_exam(exam, fields=fields, user=request.user)
        return Response({"exam": ExamSerializer(exam).data})


class ExamScheduleListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        slots = exam_q.list_schedule_slots(exam.pk)
        return Response({"slots": ExamScheduleSlotSerializer(slots, many=True).data})

    def post(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = CreateScheduleSlotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        slot, warnings, requires_override = exam_i.create_schedule_slot(
            exam,
            branch_id=branch.pk,
            class_section_id=data["classSectionId"],
            subject_id=data["subjectId"],
            date=data["date"],
            start_time=data["startTime"],
            end_time=data["endTime"],
            room_id=data["roomId"],
            max_marks=data.get("maxMarks"),
            override=data.get("override", False),
            user=request.user,
        )
        if requires_override:
            return Response({"warnings": warnings, "requiresOverride": True}, status=status.HTTP_200_OK)
        return Response(
            {"slot": ExamScheduleSlotSerializer(slot).data, "warnings": warnings},
            status=status.HTTP_201_CREATED,
        )


class ExamScheduleDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, exam_id, slot_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        slot = exam_q.get_schedule_slot(exam.pk, slot_id)
        if not slot:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = UpdateScheduleSlotSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        fields = _map_fields(data, {
            "classSectionId": "batch_id",
            "subjectId": "subject_id",
            "date": "date",
            "startTime": "start_time",
            "endTime": "end_time",
            "roomId": "room_id",
            "maxMarks": "max_marks",
            "version": "version",
        })
        slot, warnings, requires_override = exam_i.update_schedule_slot(
            slot,
            branch_id=branch.pk,
            fields=fields,
            override=data.get("override", False),
            user=request.user,
        )
        if requires_override:
            return Response({"warnings": warnings, "requiresOverride": True}, status=status.HTTP_200_OK)
        return Response({"slot": ExamScheduleSlotSerializer(slot).data, "warnings": warnings})
