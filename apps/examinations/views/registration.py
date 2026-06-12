"""Views — exam registration and hall tickets."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import structure as struct_q
from apps.academics.scoping import resolve_branch
from apps.examinations.interactors import registration as reg_i
from apps.examinations.permissions import IsAdminOrSuperAdmin
from apps.examinations.queries import exam as exam_q
from apps.examinations.queries import registration as reg_q
from apps.examinations.serializers.registration import (
    BulkRegisterSerializer,
    ExamRegistrationSerializer,
    HallTicketSerializer,
)


class ExamRegistrationListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        batch_id = request.query_params.get("classSectionId")
        registrations = reg_q.list_registrations(exam.pk, batch_id=batch_id)
        return Response({"registrations": ExamRegistrationSerializer(registrations, many=True).data})

    def post(self, request, exam_id) -> Response:
        branch = resolve_branch(request)
        exam = exam_q.get_exam(branch.pk, exam_id)
        if not exam:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        serializer = BulkRegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        batch = struct_q.get_batch(branch.pk, data["classSectionId"])
        if not batch:
            return Response({"error": "Batch not found."}, status=status.HTTP_404_NOT_FOUND)
        result = reg_i.bulk_register_exam(
            exam,
            branch=branch,
            batch_id=data["classSectionId"],
            is_arrear=data.get("isArrear", False),
            tenant=request.user.tenant,
            user=request.user,
        )
        return Response(
            {
                "registrations": ExamRegistrationSerializer(result["registrations"], many=True).data,
                "skippedStudentIds": result["skippedStudentIds"],
            },
            status=status.HTTP_201_CREATED,
        )


class HallTicketView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, registration_id) -> Response:
        branch = resolve_branch(request)
        registration = reg_q.get_registration(branch.pk, registration_id)
        if not registration:
            return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
        ticket, pdf_bytes = reg_i.generate_hall_ticket(
            registration,
            branch=branch,
            tenant=request.user.tenant,
            user=request.user,
        )
        payload = reg_i.hall_ticket_result(registration, ticket, pdf_bytes)
        return Response({"hallTicket": HallTicketSerializer(payload).data})
