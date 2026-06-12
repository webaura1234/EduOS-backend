"""Fee invoice, lines, and installments serializers."""

from rest_framework import serializers

from apps.fees.models import FeeInvoice, FeeInvoiceLine, Installment


class FeeInvoiceLineSerializer(serializers.ModelSerializer):
    amountPaise = serializers.IntegerField(source="amount_paise")

    class Meta:
        model = FeeInvoiceLine
        fields = ["id", "kind", "label", "amountPaise"]
        read_only_fields = ["id"]


class InstallmentSerializer(serializers.ModelSerializer):
    amountPaise = serializers.IntegerField(source="amount_paise")
    paidPaise = serializers.IntegerField(source="paid_paise")
    dueDate = serializers.DateField(source="due_date")

    class Meta:
        model = Installment
        fields = ["id", "sequence", "amountPaise", "paidPaise", "dueDate", "status"]
        read_only_fields = ["id", "status"]


class StudentProfileBriefSerializer(serializers.Serializer):
    # `student` is a StudentEnrollment; expose the underlying StudentProfile id.
    id = serializers.UUIDField(source="student_profile_id")
    fullName = serializers.CharField(source="user.full_name")
    phone = serializers.CharField(source="user.phone")
    email = serializers.CharField(source="user.email")
    currentBatchName = serializers.CharField(source="current_batch.name", default="", required=False)


class FeeInvoiceSerializer(serializers.ModelSerializer):
    student = StudentProfileBriefSerializer(read_only=True)
    dueDate = serializers.DateField(source="due_date")
    totalPaise = serializers.IntegerField(source="total_paise")
    paidPaise = serializers.IntegerField(source="paid_paise")
    lines = FeeInvoiceLineSerializer(many=True, read_only=True)
    installments = InstallmentSerializer(many=True, read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = FeeInvoice
        fields = [
            "id",
            "student",
            "dueDate",
            "totalPaise",
            "paidPaise",
            "status",
            "lines",
            "installments",
            "createdAt",
        ]
        read_only_fields = ["id", "student", "status", "lines", "installments", "createdAt"]
