"""Serializers — leave requests (camelCase I/O)."""

from rest_framework import serializers


class LeaveRequestSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    applicantRole = serializers.CharField(source="applicant_role", read_only=True)
    studentId = serializers.UUIDField(source="student_id", read_only=True, allow_null=True)
    employeeId = serializers.UUIDField(source="employee_id", read_only=True, allow_null=True)
    fromDate = serializers.DateField(source="from_date", read_only=True)
    toDate = serializers.DateField(source="to_date", read_only=True)
    reason = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    decisionNote = serializers.CharField(source="decision_note", read_only=True)
    approverId = serializers.UUIDField(source="approver_id", read_only=True, allow_null=True)
    approvedAt = serializers.DateTimeField(source="approved_at", read_only=True, allow_null=True)
    version = serializers.IntegerField(read_only=True)


class CreateLeaveSerializer(serializers.Serializer):
    studentId = serializers.UUIDField()
    fromDate = serializers.DateField()
    toDate = serializers.DateField()
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class ReviewLeaveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    note = serializers.CharField(required=False, allow_blank=True, default="")
    version = serializers.IntegerField(required=False)


class AuditEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    recordId = serializers.UUIDField(source="record_id", read_only=True)
    auditType = serializers.CharField(source="audit_type", read_only=True)
    originalStatus = serializers.CharField(source="original_status", read_only=True, allow_null=True)
    newStatus = serializers.CharField(source="new_status", read_only=True, allow_null=True)
    reason = serializers.CharField(read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
