"""Concession and credit note serializers."""

from rest_framework import serializers

from apps.fees.models import ConcessionRequest, ConcessionRule, CreditNote


class ConcessionRuleSerializer(serializers.ModelSerializer):
    amountPaise = serializers.IntegerField(source="amount_paise", required=False, allow_null=True)
    percent = serializers.IntegerField(required=False, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = ConcessionRule
        fields = ["id", "name", "amountPaise", "percent", "criteria", "createdAt"]
        read_only_fields = ["id", "createdAt"]


class ConcessionRequestSerializer(serializers.ModelSerializer):
    student = serializers.UUIDField(source="student_id")
    rule = serializers.UUIDField(source="rule_id", required=False, allow_null=True)
    amountPaise = serializers.IntegerField(source="amount_paise")
    requestedBy = serializers.UUIDField(source="requested_by_id", read_only=True)
    approver = serializers.UUIDField(source="approver_id", read_only=True)
    decidedAt = serializers.DateTimeField(source="decided_at", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = ConcessionRequest
        fields = [
            "id",
            "student",
            "rule",
            "amountPaise",
            "status",
            "requestedBy",
            "approver",
            "decidedAt",
            "note",
            "createdAt",
        ]
        read_only_fields = ["id", "status", "requestedBy", "approver", "decidedAt", "createdAt"]


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
