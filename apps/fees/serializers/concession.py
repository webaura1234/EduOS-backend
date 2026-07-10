"""Concession and credit note serializers."""

from rest_framework import serializers

from apps.fees.models import ConcessionRule, CreditNote, StudentConcession


class ConcessionRuleSerializer(serializers.ModelSerializer):
    amountPaise = serializers.IntegerField(source="amount_paise", required=False, allow_null=True)
    percent = serializers.IntegerField(required=False, allow_null=True)
    active = serializers.BooleanField(source="is_active", required=False)
    studentsUsing = serializers.IntegerField(source="students_using", read_only=True, required=False)
    totalGrantedPaise = serializers.IntegerField(source="total_granted_paise", read_only=True, required=False)
    lastAppliedAt = serializers.DateTimeField(source="last_applied_at", read_only=True, required=False)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = ConcessionRule
        fields = [
            "id", "name", "amountPaise", "percent", "criteria", "active",
            "studentsUsing", "totalGrantedPaise", "lastAppliedAt", "createdAt",
        ]
        read_only_fields = ["id", "studentsUsing", "totalGrantedPaise", "lastAppliedAt", "createdAt"]


class StudentConcessionSerializer(serializers.ModelSerializer):
    student = serializers.UUIDField(source="student_id", write_only=True)
    rule = serializers.UUIDField(source="rule_id")
    amountPaise = serializers.IntegerField(source="amount_paise", required=False)
    reason = serializers.CharField(source="note", required=False, allow_blank=True)
    appliedBy = serializers.UUIDField(source="approver_id", read_only=True)
    appliedAt = serializers.DateTimeField(source="decided_at", read_only=True)
    createdBy = serializers.UUIDField(source="requested_by_id", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = StudentConcession
        fields = [
            "id",
            "student",
            "rule",
            "amountPaise",
            "status",
            "reason",
            "createdBy",
            "appliedBy",
            "appliedAt",
            "createdAt",
        ]
        read_only_fields = ["id", "status", "amountPaise", "createdBy", "appliedBy", "appliedAt", "createdAt"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.student_id:
            data["student"] = str(instance.student.student_profile_id)
        if instance.rule_id:
            data["ruleName"] = instance.rule.name if instance.rule else ""
        data["studentName"] = ""
        if instance.student_id and hasattr(instance.student, "student_profile"):
            profile = instance.student.student_profile
            user = getattr(profile, "user", None)
            if user:
                data["studentName"] = user.full_name or user.email or ""
        return data


# Deprecated alias
ConcessionRequestSerializer = StudentConcessionSerializer


class BulkApplyStudentConcessionSerializer(serializers.Serializer):
    studentIds = serializers.ListField(child=serializers.UUIDField(), min_length=1)
    ruleId = serializers.UUIDField()
    reason = serializers.CharField()


class CreditNoteSerializer(serializers.ModelSerializer):
    student = serializers.UUIDField(source="student_id")
    invoice = serializers.UUIDField(source="invoice_id")
    amountPaise = serializers.IntegerField(source="amount_paise")
    approvedBy = serializers.UUIDField(source="approved_by_id", read_only=True)
    decidedAt = serializers.DateTimeField(source="decided_at", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = CreditNote
        fields = [
            "id",
            "student",
            "invoice",
            "amountPaise",
            "reason",
            "status",
            "approvedBy",
            "decidedAt",
            "createdAt",
        ]
        read_only_fields = ["id", "status", "approvedBy", "decidedAt", "createdAt"]

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.student_id:
            data["student"] = str(instance.student.student_profile_id)
        return data
