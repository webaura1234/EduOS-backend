"""Serializers — exam registration and hall tickets (camelCase)."""

from rest_framework import serializers


class ExamRegistrationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    examId = serializers.UUIDField(source="exam_id", read_only=True)
    # `student` is a StudentEnrollment; expose the StudentProfile id (stable API).
    studentId = serializers.UUIDField(source="student.student_profile_id", read_only=True)
    enrollmentId = serializers.UUIDField(source="student_id", read_only=True)
    studentName = serializers.CharField(source="student.user.full_name", read_only=True)
    classSectionId = serializers.UUIDField(source="student.current_batch_id", read_only=True)
    classLabel = serializers.CharField(source="student.current_batch.name", read_only=True)
    feeInvoiceId = serializers.UUIDField(source="fee_invoice_id", read_only=True, allow_null=True)
    feePaid = serializers.BooleanField(source="fee_paid", read_only=True)
    isArrear = serializers.BooleanField(source="is_arrear", read_only=True)
    version = serializers.IntegerField(read_only=True)


class BulkRegisterSerializer(serializers.Serializer):
    classSectionId = serializers.UUIDField()
    isArrear = serializers.BooleanField(required=False, default=False)


class HallTicketSerializer(serializers.Serializer):
    studentId = serializers.CharField()
    studentName = serializers.CharField()
    canDownload = serializers.BooleanField()
    blockedReason = serializers.CharField(required=False, allow_null=True)
    content = serializers.CharField()
    fileKey = serializers.CharField(required=False)
    rollNumber = serializers.CharField(required=False)
    generatedAt = serializers.CharField()
