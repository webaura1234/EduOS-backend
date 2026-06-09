"""Serializers — Department, Course, Batch (camelCase I/O)."""

from rest_framework import serializers

from apps.academics.models import DepartmentType


class DepartmentSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    departmentType = serializers.CharField(source="department_type", read_only=True)
    headFacultyId = serializers.UUIDField(source="head_faculty_id", read_only=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)


class CreateDepartmentSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    code = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    departmentType = serializers.ChoiceField(choices=DepartmentType.values, required=False,
                                             default=DepartmentType.DEPARTMENT)
    headFacultyId = serializers.UUIDField(required=False, allow_null=True)


class CourseSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    departmentId = serializers.UUIDField(source="department_id", read_only=True)
    name = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    durationYears = serializers.IntegerField(source="duration_years", read_only=True)
    regulation = serializers.CharField(read_only=True)
    totalCredits = serializers.IntegerField(source="total_credits", read_only=True, allow_null=True)


class CreateCourseSerializer(serializers.Serializer):
    departmentId = serializers.UUIDField()
    name = serializers.CharField(max_length=150)
    code = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    durationYears = serializers.IntegerField(required=False, default=1, min_value=1)
    regulation = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    totalCredits = serializers.IntegerField(required=False, allow_null=True)


class BatchSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    courseId = serializers.UUIDField(source="course_id", read_only=True)
    academicYearId = serializers.UUIDField(source="academic_year_id", read_only=True)
    name = serializers.CharField(read_only=True)
    capacity = serializers.IntegerField(read_only=True)
    classTeacherId = serializers.UUIDField(source="class_teacher_id", read_only=True, allow_null=True)


class CreateBatchSerializer(serializers.Serializer):
    courseId = serializers.UUIDField()
    academicYearId = serializers.UUIDField()
    name = serializers.CharField(max_length=50)
    capacity = serializers.IntegerField(required=False, default=40, min_value=1)
    classTeacherId = serializers.UUIDField(required=False, allow_null=True)
