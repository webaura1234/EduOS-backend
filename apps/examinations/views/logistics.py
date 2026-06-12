"""Views — seating generation and invigilator assignment."""

from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.examinations.interactors import invigilator as inv_i
from apps.examinations.interactors import seating as seat_i
from apps.examinations.permissions import IsAdminOrSuperAdmin
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import invigilator as inv_q
from apps.examinations.serializers.logistics import (
    AssignInvigilatorSerializer,
    GenerateSeatingSerializer,
    InvigilationAssignmentSerializer,
    SeatingPlanSerializer,
)


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
        plans = seat_i.generate_seating_for_exam(
            exam,
            branch_id=branch.pk,
            exam_slot_id=data.get("examSlotId"),
            room_ids=data.get("roomIds"),
            user=request.user,
        )
        return Response(
            {"seatingPlans": SeatingPlanSerializer(plans, many=True).data},
            status=status.HTTP_201_CREATED,
        )


class ExamInvigilatorView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        duties = inv_q.list_duties_for_exam(exam.pk)
        payload = [
            {
                "examSlotId": str(d.schedule_slot_id),
                "facultyId": str(d.faculty_id),
                "facultyName": d.faculty.full_name,
                "assignedAt": d.created_at.isoformat(),
                "assignedBy": "auto",
            }
            for d in duties
        ]
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
            assignments = inv_i.auto_assign_invigilators(
                exam,
                branch=branch,
                tenant_id=request.user.tenant_id,
                user=request.user,
            )
            return Response(
                {"invigilation": InvigilationAssignmentSerializer(assignments, many=True).data},
                status=status.HTTP_201_CREATED,
            )

        slot_id = data.get("examSlotId")
        faculty_id = data.get("facultyId")
        if not slot_id or not faculty_id:
            raise ValidationError(
                {"examSlotId": "examSlotId and facultyId are required unless autoAssign is true."}
            )

        slot = exam_q.get_schedule_slot(exam.pk, slot_id)
        if not slot:
            return Response({"error": "Schedule slot not found."}, status=status.HTTP_404_NOT_FOUND)

        assignment = inv_i.assign_invigilator_manual(
            exam=exam,
            slot=slot,
            branch=branch,
            tenant_id=request.user.tenant_id,
            faculty_id=faculty_id,
            user=request.user,
        )
        return Response(
            {"invigilation": InvigilationAssignmentSerializer([assignment], many=True).data},
            status=status.HTTP_201_CREATED,
        )
