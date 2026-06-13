"""Serializers — Employee + BranchFaculty (camelCase I/O)."""

from rest_framework import serializers

from apps.hr.enums import EmploymentType


class EmployeeSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    userId = serializers.UUIDField(source="user_id", read_only=True)
    name = serializers.CharField(source="user.full_name", read_only=True)
    branchId = serializers.UUIDField(source="branch_id", read_only=True)
    employeeCode = serializers.CharField(source="employee_code", read_only=True)
    employmentType = serializers.CharField(source="employment_type", read_only=True)
    designation = serializers.CharField(read_only=True)
    joinedAt = serializers.DateField(source="joined_at", read_only=True)
    exitedAt = serializers.DateField(source="exited_at", read_only=True, allow_null=True)
    baseComponents = serializers.JSONField(source="base_components", read_only=True)
    isActive = serializers.BooleanField(source="is_active", read_only=True)
    version = serializers.IntegerField(read_only=True)


class CreateEmployeeSerializer(serializers.Serializer):
    userId = serializers.UUIDField()
    employeeCode = serializers.CharField(max_length=50)
    employmentType = serializers.ChoiceField(choices=EmploymentType.values,
                                             default=EmploymentType.FULL_TIME)
    designation = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    joinedAt = serializers.DateField()
    baseComponents = serializers.JSONField(required=False, default=list)
    bankAccount = serializers.CharField(required=False, allow_blank=True, default="")
    ifsc = serializers.CharField(required=False, allow_blank=True, default="")
    pan = serializers.CharField(required=False, allow_blank=True, default="")


class DeactivateEmployeeSerializer(serializers.Serializer):
    exitedAt = serializers.DateField(required=False, allow_null=True)


class AssignBranchSerializer(serializers.Serializer):
    facultyId = serializers.UUIDField()
    branchId = serializers.UUIDField()
    isSalaryBranch = serializers.BooleanField(required=False, default=False)
    roleAtBranch = serializers.JSONField(required=False, default=dict)


class BranchFacultySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    facultyId = serializers.UUIDField(source="faculty_id", read_only=True)
    branchId = serializers.UUIDField(source="branch_id", read_only=True)
    isSalaryBranch = serializers.BooleanField(source="is_salary_branch", read_only=True)
