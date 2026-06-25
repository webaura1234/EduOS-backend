"""Serializers — Enquiry (camelCase)."""

from rest_framework import serializers

from apps.admissions.enums import EnquirySource, EnquiryStatus


class EnquirySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    branchId = serializers.UUIDField(source="branch_id", read_only=True)
    source = serializers.ChoiceField(choices=EnquirySource.choices)
    courseId = serializers.UUIDField(source="course_id", allow_null=True)
    courseName = serializers.CharField(source="course.name", read_only=True, allow_null=True)
    applicantName = serializers.CharField(source="applicant_name")
    dateOfBirth = serializers.DateField(source="date_of_birth", allow_null=True, required=False)
    phone = serializers.CharField(allow_blank=True, required=False, default="")
    email = serializers.EmailField(allow_blank=True, required=False, default="")
    status = serializers.ChoiceField(choices=EnquiryStatus.choices, read_only=True)
    capturedById = serializers.UUIDField(source="captured_by_id", read_only=True, allow_null=True)
    notes = serializers.CharField(allow_blank=True, required=False, default="")
    version = serializers.IntegerField(read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)


class CreateEnquirySerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=EnquirySource.choices)
    courseId = serializers.UUIDField(required=False, allow_null=True)
    courseName = serializers.CharField(required=False, allow_blank=True, default="")
    applicantName = serializers.CharField(max_length=150)
    dateOfBirth = serializers.DateField(required=False, allow_null=True)
    phone = serializers.CharField(required=False, allow_blank=True, default="")
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class UpdateEnquirySerializer(serializers.Serializer):
    source = serializers.ChoiceField(choices=EnquirySource.choices, required=False)
    courseId = serializers.UUIDField(required=False, allow_null=True)
    applicantName = serializers.CharField(max_length=150, required=False)
    dateOfBirth = serializers.DateField(required=False, allow_null=True)
    phone = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    status = serializers.ChoiceField(choices=EnquiryStatus.choices, required=False)
    notes = serializers.CharField(required=False, allow_blank=True)
    version = serializers.IntegerField(required=False)
