"""Fee structure and assignment serializers."""

from rest_framework import serializers

from apps.fees.models import FeeStructure, StudentFeeAssignment


class FeeStructureSerializer(serializers.ModelSerializer):
    academicYear = serializers.UUIDField(source="academic_year_id")
    batch = serializers.UUIDField(source="batch_id", required=False, allow_null=True)
    totalPaise = serializers.IntegerField(source="total_paise", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)

    class Meta:
        model = FeeStructure
        fields = [
            "id",
            "name",
            "batch",
            "academicYear",
            "components",
            "version",
            "totalPaise",
            "createdAt",
            "updatedAt",
        ]
        read_only_fields = ["id", "version", "createdAt", "updatedAt"]


class StudentFeeAssignmentSerializer(serializers.ModelSerializer):
    student = serializers.UUIDField(source="student_id")
    feeStructure = serializers.UUIDField(source="fee_structure_id")
    structureSnapshot = serializers.JSONField(source="structure_snapshot", read_only=True)
    discountLines = serializers.JSONField(source="discount_lines", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    class Meta:
        model = StudentFeeAssignment
        fields = [
            "id",
            "student",
            "feeStructure",
            "structureSnapshot",
            "discountLines",
            "createdAt",
        ]
        read_only_fields = ["id", "structureSnapshot", "discountLines", "createdAt"]

    def to_representation(self, instance):
        # `student` FK is a StudentEnrollment; expose the StudentProfile id (stable API).
        data = super().to_representation(instance)
        if instance.student_id:
            data["student"] = str(instance.student.student_profile_id)
        return data
