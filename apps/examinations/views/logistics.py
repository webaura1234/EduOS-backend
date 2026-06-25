"""Views — seating generation and invigilator assignment."""

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.examinations.interactors import invigilator as inv_i
from apps.examinations.interactors import seating as seat_i
from apps.examinations.interactors import seating_session as session_i
from apps.examinations.permissions import IsAdminOrSuperAdmin
from apps.examinations.queries import exam as exam_q
from apps.examinations.serializers.logistics import (
    AssignInvigilatorSerializer,
    CreateSeatingSessionSerializer,
    GenerateSeatingSerializer,
    InvigilationAssignmentSerializer,
    PreflightSeatingSerializer,
    SeatingBulkErrorSerializer,
    SeatingPlanSerializer,
    SeatingPreflightSerializer,
    SeatingSessionSerializer,
)


class ExamSeatingListView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        plans = seat_i.list_plans_for_exam(exam.pk)
        return Response({"seatingPlans": SeatingPlanSerializer(plans, many=True).data})


class ExamSeatingPreflightView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = PreflightSeatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        report = seat_i.preflight_seating(
            exam, branch_id=branch.pk, slot_ids=data.get("examSlotIds")
        )
        return Response({"preflight": SeatingPreflightSerializer(report).data})


class ExamSeatingGenerateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = GenerateSeatingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = seat_i.generate_seating_for_exam(
            exam,
            branch_id=branch.pk,
            exam_slot_id=data.get("examSlotId"),
            exam_slot_ids=data.get("examSlotIds"),
            room_ids=data.get("roomIds"),
            mode=data.get("mode", "per_slot"),
            seating_order=data.get("seatingOrder", "random"),
            seed=data.get("seed"),
            user=request.user,
        )
        payload = {
            "seatingPlans": SeatingPlanSerializer(result.get("seatingPlans", []), many=True).data,
            "errors": SeatingBulkErrorSerializer(result.get("errors", []), many=True).data,
        }
        if "hallAllocations" in result:
            payload["hallAllocations"] = result["hallAllocations"]
        if "unallocated" in result:
            payload["unallocated"] = result["unallocated"]
        return Response(payload, status=status.HTTP_201_CREATED)


class ExamSeatingSessionView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = CreateSeatingSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = session_i.create_seating_session(
            exam,
            branch_id=branch.pk,
            name=data.get("name", ""),
            hall_room_id=data["hallRoomId"],
            slot_ids=data["examSlotIds"],
            user=request.user,
        )
        return Response(
            {"session": SeatingSessionSerializer(result["session"]).data},
            status=status.HTTP_201_CREATED,
        )


class ExamInvigilatorView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        payload = inv_i.list_invigilation_for_exam(exam.pk)
        return Response({"invigilation": InvigilationAssignmentSerializer(payload, many=True).data})

    def post(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = AssignInvigilatorSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if data.get("autoAssign"):
            inv_i.auto_assign_invigilators(
                exam,
                branch=branch,
                tenant_id=request.user.tenant_id,
                user=request.user,
            )
            payload = inv_i.list_invigilation_for_exam(exam.pk)
            return Response(
                {"invigilation": InvigilationAssignmentSerializer(payload, many=True).data},
                status=status.HTTP_201_CREATED,
            )

        slot_id = data.get("examSlotId")
        faculty_id = data.get("facultyId")
        mode = data.get("mode", "add")
        if not slot_id or not faculty_id:
            raise ValidationError(
                {"examSlotId": "examSlotId and facultyId are required unless autoAssign is true."}
            )

        slot = exam_q.get_schedule_slot(exam.pk, slot_id)
        if not slot:
            return Response({"error": "Schedule slot not found."}, status=status.HTTP_404_NOT_FOUND)

        if mode == "add":
            inv_i.add_invigilator(
                exam=exam,
                slot=slot,
                branch=branch,
                tenant_id=request.user.tenant_id,
                faculty_id=faculty_id,
                user=request.user,
            )
        elif mode == "replace":
            inv_i.replace_invigilator(
                exam=exam,
                slot=slot,
                branch=branch,
                tenant_id=request.user.tenant_id,
                faculty_id=faculty_id,
                replace_faculty_id=data.get("replaceFacultyId"),
                user=request.user,
            )
        elif mode == "remove":
            inv_i.remove_invigilator(
                exam=exam,
                slot=slot,
                branch=branch,
                tenant_id=request.user.tenant_id,
                faculty_id=faculty_id,
                user=request.user,
            )
        else:
            raise ValidationError({"mode": "Invalid mode."})

        payload = inv_i.list_invigilation_for_exam(exam.pk)
        return Response(
            {"invigilation": InvigilationAssignmentSerializer(payload, many=True).data},
            status=status.HTTP_201_CREATED,
        )
