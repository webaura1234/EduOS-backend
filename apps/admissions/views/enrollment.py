"""Views — StudentEnrollment, Provisioning, Transfer, and Sibling override."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries.structure import get_batch
from apps.academics.queries.rollover import get_academic_year
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.admissions.interactors.enrollment import ProvisionEnrollmentInteractor, transfer_enrollment
from apps.admissions.interactors.duplicate_detection import resolve_sibling_group_id
from apps.admissions.queries import enrollment as enr_q
from apps.admissions.serializers.enrollment import (
    ProvisionEnrollmentSerializer,
    SiblingOverrideSerializer,
    StudentEnrollmentSerializer,
    TransferEnrollmentSerializer,
)


class EnrollmentListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        batch_id = request.query_params.get("batchId")
        year_id = request.query_params.get("academicYearId")
        enrollments = enr_q.list_enrollments(branch.pk, batch_id=batch_id, academic_year_id=year_id)
        return Response({"enrollments": StudentEnrollmentSerializer(enrollments, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        serializer = ProvisionEnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        batch = get_batch(branch.pk, data["batchId"])
        if not batch:
            return Response({"error": "Batch not found."}, status=status.HTTP_400_BAD_REQUEST)
            
        academic_year = get_academic_year(data["academicYearId"])
        if not academic_year:
            return Response({"error": "Academic year not found."}, status=status.HTTP_400_BAD_REQUEST)
            
        interactor = ProvisionEnrollmentInteractor(
            branch=branch,
            batch=batch,
            academic_year=academic_year,
            admission_number=data["admissionNumber"],
            first_name=data["firstName"],
            last_name=data.get("lastName", ""),
            date_of_birth=data.get("dateOfBirth"),
            gender=data.get("gender", ""),
            student_phone=data.get("studentPhone"),
            student_email=data.get("studentEmail"),
            parent_name=data["parentName"],
            parent_phone=data.get("parentPhone"),
            parent_email=data.get("parentEmail"),
            fee_structure_id=data.get("feeStructureId"),
            confirm_linked=data.get("confirmLinked", False),
            confirm_duplicate=data.get("confirmDuplicate", False),
            sibling_group_id=data.get("siblingGroupId"),
            user=request.user,
        )
        result = interactor.execute()
        return Response(result, status=status.HTTP_201_CREATED)


class EnrollmentDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, enrollment_id) -> Response:
        enrollment = enr_q.get_enrollment_by_id(enrollment_id)
        if not enrollment:
            return Response({"error": "Enrollment not found."}, status=status.HTTP_404_NOT_FOUND)
        
        if str(enrollment.branch.tenant_id) != str(request.user.tenant_id):
            return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            
        return Response({"enrollment": StudentEnrollmentSerializer(enrollment).data})


class EnrollmentTransferView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, enrollment_id) -> Response:
        branch = resolve_branch(request)
        enrollment = enr_q.get_enrollment_by_id(enrollment_id)
        if not enrollment or enrollment.branch_id != branch.pk:
            return Response({"error": "Enrollment not found."}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = TransferEnrollmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        to_branch = resolve_branch(request, data["toBranchId"])
        to_batch = get_batch(to_branch.pk, data["toBatchId"])
        if not to_batch:
            return Response({"error": "Target batch not found."}, status=status.HTTP_400_BAD_REQUEST)
            
        academic_year = get_academic_year(data["academicYearId"])
        if not academic_year:
            return Response({"error": "Academic year not found."}, status=status.HTTP_400_BAD_REQUEST)
            
        new_enrollment = transfer_enrollment(
            enrollment=enrollment,
            to_branch=to_branch,
            to_batch=to_batch,
            academic_year=academic_year,
            user=request.user,
        )
        return Response({"enrollment": StudentEnrollmentSerializer(new_enrollment).data})


class SiblingOverrideView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        serializer = SiblingOverrideSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        sibling_group_id = resolve_sibling_group_id(
            branch_id=branch.pk,
            sibling_student_profile_id=serializer.validated_data["siblingStudentProfileId"],
            user=request.user,
        )
        return Response({"siblingGroupId": sibling_group_id})
