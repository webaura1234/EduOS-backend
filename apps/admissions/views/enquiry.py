"""Views — Enquiry management."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries.structure import get_course
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.admissions.interactors import enquiry as enquiry_i
from apps.admissions.queries import enquiry as enquiry_q
from apps.admissions.serializers.enquiry import (
    CreateEnquirySerializer,
    EnquirySerializer,
    UpdateEnquirySerializer,
)
from apps.admissions.serializers.application import ApplicationSerializer


def _map_fields(data, mapping):
    return {django_field: data[api_field] for api_field, django_field in mapping.items() if api_field in data}


class EnquiryListCreateView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        status_filter = request.query_params.get("status")
        source_filter = request.query_params.get("source")
        enquiries = enquiry_q.list_enquiries(branch.pk, status=status_filter, source=source_filter)
        return Response({"enquiries": EnquirySerializer(enquiries, many=True).data})

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        serializer = CreateEnquirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        
        course = None
        if data.get("courseId"):
            course = get_course(branch.pk, data["courseId"])
            
        enquiry = enquiry_i.capture_enquiry(
            branch=branch,
            source=data["source"],
            applicant_name=data["applicantName"],
            course=course,
            date_of_birth=data.get("dateOfBirth"),
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            captured_by=request.user,
            notes=data.get("notes", ""),
        )
        return Response({"enquiry": EnquirySerializer(enquiry).data}, status=status.HTTP_201_CREATED)


class EnquiryDetailView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def patch(self, request, enquiry_id) -> Response:
        branch = resolve_branch(request)
        enquiry = enquiry_q.get_enquiry(branch.pk, enquiry_id)
        if not enquiry:
            return Response({"error": "Enquiry not found."}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = UpdateEnquirySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        fields = _map_fields(serializer.validated_data, {
            "source": "source",
            "courseId": "course_id",
            "applicantName": "applicant_name",
            "dateOfBirth": "date_of_birth",
            "phone": "phone",
            "email": "email",
            "status": "status",
            "notes": "notes",
            "version": "version",
        })
        
        if "course_id" in fields and fields["course_id"]:
            course = get_course(branch.pk, fields["course_id"])
            if not course:
                return Response({"error": "Course not found."}, status=status.HTTP_400_BAD_REQUEST)
            fields["course"] = course
            del fields["course_id"]
            
        enquiry = enquiry_q.update_enquiry(enquiry, fields, user=request.user)
        return Response({"enquiry": EnquirySerializer(enquiry).data})


class EnquiryConvertView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request, enquiry_id) -> Response:
        branch = resolve_branch(request)
        enquiry = enquiry_q.get_enquiry(branch.pk, enquiry_id)
        if not enquiry:
            return Response({"error": "Enquiry not found."}, status=status.HTTP_404_NOT_FOUND)
        
        course_id = request.data.get("courseId")
        course = None
        if course_id:
            course = get_course(branch.pk, course_id)
            if not course:
                return Response({"error": "Course not found."}, status=status.HTTP_400_BAD_REQUEST)
                
        application = enquiry_i.convert_enquiry_to_application(
            enquiry=enquiry,
            course=course,
            user=request.user,
        )
        return Response({"application": ApplicationSerializer(application).data}, status=status.HTTP_201_CREATED)
