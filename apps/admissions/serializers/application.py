"""Serializers — Application, ApplicationDocument, and Waitlist (camelCase)."""

from rest_framework import serializers

from apps.admissions.enums import ApplicationStatus, DocVerificationStatus
from apps.admissions.serializers.enquiry import EnquirySerializer


class ApplicationDocumentSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    applicationId = serializers.UUIDField(source="application_id", read_only=True)
    docType = serializers.CharField(source="doc_type")
    s3Key = serializers.CharField(source="s3_key", required=False, allow_blank=True)
    verificationStatus = serializers.ChoiceField(
        source="verification_status", choices=DocVerificationStatus.choices, read_only=True
    )
    verifiedById = serializers.UUIDField(source="verified_by_id", read_only=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)


class ApplicationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    branchId = serializers.UUIDField(source="branch_id", read_only=True)
    enquiryId = serializers.UUIDField(source="enquiry_id", read_only=True)
    enquiry = EnquirySerializer(read_only=True)
    courseId = serializers.UUIDField(source="course_id", allow_null=True)
    courseName = serializers.CharField(source="course.name", read_only=True, allow_null=True)
    step = serializers.JSONField(required=False)
    eligibilityResult = serializers.JSONField(source="eligibility_result", required=False)
    status = serializers.ChoiceField(choices=ApplicationStatus.choices, read_only=True)
    rejectionReason = serializers.CharField(source="rejection_reason", read_only=True)
    documents = ApplicationDocumentSerializer(many=True, read_only=True)
    version = serializers.IntegerField(read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)


class SaveApplicationStepSerializer(serializers.Serializer):
    step = serializers.JSONField()


class AddDocumentSerializer(serializers.Serializer):
    docType = serializers.CharField(max_length=50)
    s3Key = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class VerifyDocumentSerializer(serializers.Serializer):
    verificationStatus = serializers.ChoiceField(choices=DocVerificationStatus.choices)


class RejectApplicationSerializer(serializers.Serializer):
    rejectionReason = serializers.CharField()


class WaitlistSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    branchId = serializers.UUIDField(source="branch_id", read_only=True)
    applicationId = serializers.UUIDField(source="application_id", read_only=True)
    courseId = serializers.UUIDField(source="course_id", read_only=True)
    courseName = serializers.CharField(source="course.name", read_only=True)
    rank = serializers.IntegerField(read_only=True)
    applicantName = serializers.CharField(source="application.enquiry.applicant_name", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
