"""Serializers — StudentEnrollment, Provisioning, and Transfer (camelCase)."""

from rest_framework import serializers

from apps.admissions.enums import EnrollmentStatus


class StudentEnrollmentSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    branchId = serializers.UUIDField(source="branch_id", read_only=True)
    studentProfileId = serializers.UUIDField(source="student_profile_id", read_only=True)
    studentName = serializers.SerializerMethodField()
    batchId = serializers.UUIDField(source="batch_id", allow_null=True)
    batchName = serializers.CharField(source="batch.name", read_only=True, allow_null=True)
    academicYearId = serializers.UUIDField(source="academic_year_id")
    academicYearLabel = serializers.CharField(source="academic_year.name", read_only=True)
    applicationId = serializers.UUIDField(source="application_id", allow_null=True)
    feeStructureSnapshotId = serializers.UUIDField(source="fee_structure_snapshot_id", allow_null=True)
    status = serializers.ChoiceField(choices=EnrollmentStatus.choices, read_only=True)
    isTransferred = serializers.BooleanField(source="is_transferred", read_only=True)
    transferredFromBranchId = serializers.UUIDField(source="transferred_from_branch_id", read_only=True, allow_null=True)
    transferredFromBranchName = serializers.CharField(source="transferred_from_branch.name", read_only=True, allow_null=True)
    backlogSubjects = serializers.JSONField(source="backlog_subjects", read_only=True)
    siblingGroupId = serializers.UUIDField(source="sibling_group_id", read_only=True, allow_null=True)
    version = serializers.IntegerField(read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)

    def get_studentName(self, obj) -> str:
        u = obj.student_profile.user
        return f"{u.first_name} {u.last_name}".strip()


class ProvisionEnrollmentSerializer(serializers.Serializer):
    batchId = serializers.UUIDField()
    academicYearId = serializers.UUIDField()
    admissionNumber = serializers.CharField(max_length=50)
    firstName = serializers.CharField(max_length=150)
    lastName = serializers.CharField(max_length=150, required=False, default="", allow_blank=True)
    dateOfBirth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.CharField(max_length=20, required=False, default="", allow_blank=True)
    studentPhone = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    studentEmail = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    parentName = serializers.CharField(max_length=150)
    parentPhone = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    parentEmail = serializers.EmailField(required=False, allow_null=True, allow_blank=True)
    feeStructureId = serializers.UUIDField(required=False, allow_null=True)
    applicationId = serializers.UUIDField(required=False, allow_null=True)
    confirmLinked = serializers.BooleanField(required=False, default=False)
    confirmDuplicate = serializers.BooleanField(required=False, default=False)
    siblingGroupId = serializers.UUIDField(required=False, allow_null=True)


class TransferEnrollmentSerializer(serializers.Serializer):
    toBranchId = serializers.UUIDField()
    toBatchId = serializers.UUIDField()
    academicYearId = serializers.UUIDField()


class SiblingOverrideSerializer(serializers.Serializer):
    siblingStudentProfileId = serializers.UUIDField()
