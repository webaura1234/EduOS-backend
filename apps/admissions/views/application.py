"""Views — Application, Document Upload, Verification, and Rejection/Enrollment."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries.structure import get_batch
from apps.academics.queries.rollover import get_academic_year
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.admissions.interactors import application as app_i
from apps.admissions.interactors.enrollment import ProvisionEnrollmentInteractor
from apps.admissions.queries import application as app_q
from apps.admissions.serializers.application import (
    AddDocumentSerializer,
    ApplicationSerializer,
    RejectApplicationSerializer,
    SaveApplicationStepSerializer,
    VerifyDocumentSerializer,
)
from apps.admissions.serializers.enrollment import ProvisionEnrollmentSerializer


class ApplicationListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        status_filter = request.query_params.get("status")
        course_id = request.query_params.get("courseId")
        apps = app_q.list_applications(branch.pk, status=status_filter, course_id=course_id)
        return Response({"applications": ApplicationSerializer(apps, many=True).data})


class ApplicationDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request, application_id) -> Response:
        branch = resolve_branch(request)
        application = app_q.get_application(branch.pk, application_id)
        if not application:
            return Response({"error": "Application not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"application": ApplicationSerializer(application).data})


class ApplicationStepView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, application_id) -> Response:
        branch = resolve_branch(request)
        serializer = SaveApplicationStepSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        application = app_i.save_application_step(
            branch_id=branch.pk,
            application_id=application_id,
            step=serializer.validated_data["step"],
            user=request.user,
        )
        return Response({"application": ApplicationSerializer(application).data})


class ApplicationDocumentView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, application_id) -> Response:
        branch = resolve_branch(request)
        serializer = AddDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        document = app_i.add_application_document(
            branch_id=branch.pk,
            application_id=application_id,
            doc_type=data["docType"],
            s3_key=data.get("s3Key", ""),
            user=request.user,
        )
        from apps.admissions.serializers.application import ApplicationDocumentSerializer
        return Response({"document": ApplicationDocumentSerializer(document).data}, status=status.HTTP_201_CREATED)


class DocumentVerifyView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, document_id) -> Response:
        branch = resolve_branch(request)
        serializer = VerifyDocumentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        document = app_i.verify_document(
            branch_id=branch.pk,
            document_id=document_id,
            verification_status=serializer.validated_data["verificationStatus"],
            user=request.user,
        )
        from apps.admissions.serializers.application import ApplicationDocumentSerializer
        return Response({"document": ApplicationDocumentSerializer(document).data})


class ApplicationRejectView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, application_id) -> Response:
        branch = resolve_branch(request)
        serializer = RejectApplicationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        application = app_i.reject_application(
            branch_id=branch.pk,
            application_id=application_id,
            rejection_reason=serializer.validated_data["rejectionReason"],
            user=request.user,
        )
        return Response({"application": ApplicationSerializer(application).data})


class ApplicationEnrollView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, application_id) -> Response:
        branch = resolve_branch(request)
        application = app_q.get_application(branch.pk, application_id)
        if not application:
            return Response({"error": "Application not found."}, status=status.HTTP_404_NOT_FOUND)
            
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
            application=application,
            confirm_linked=data.get("confirmLinked", False),
            confirm_duplicate=data.get("confirmDuplicate", False),
            sibling_group_id=data.get("siblingGroupId"),
            user=request.user,
        )
        result = interactor.execute()
        return Response(result, status=status.HTTP_201_CREATED)
