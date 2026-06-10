"""Serializers — Subject, BatchSubject, BatchFaculty (camelCase I/O)."""

from rest_framework import serializers

from apps.academics.models import BatchFacultyRole, SubjectType


class SubjectSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    courseId = serializers.UUIDField(source="course_id", read_only=True)
    name = serializers.CharField(read_only=True)
    code = serializers.CharField(read_only=True)
    subjectType = serializers.CharField(source="subject_type", read_only=True)
    maxMarks = serializers.IntegerField(source="max_marks", read_only=True)
    passMarks = serializers.IntegerField(source="pass_marks", read_only=True)
    credits = serializers.IntegerField(read_only=True, allow_null=True)
    isElective = serializers.BooleanField(source="is_elective", read_only=True)


class UpdateSubjectSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    code = serializers.CharField(max_length=20, required=False, allow_blank=True)
    subjectType = serializers.ChoiceField(choices=SubjectType.values, required=False)
    maxMarks = serializers.IntegerField(required=False, min_value=1)
    passMarks = serializers.IntegerField(required=False, min_value=0)
    credits = serializers.IntegerField(required=False, allow_null=True)
    isElective = serializers.BooleanField(required=False)
    version = serializers.IntegerField(required=False)


class CreateSubjectSerializer(serializers.Serializer):
    courseId = serializers.UUIDField()
    name = serializers.CharField(max_length=150)
    code = serializers.CharField(max_length=20, required=False, allow_blank=True, default="")
    subjectType = serializers.ChoiceField(choices=SubjectType.values, required=False,
                                          default=SubjectType.THEORY)
    maxMarks = serializers.IntegerField(required=False, default=100, min_value=1)
    passMarks = serializers.IntegerField(required=False, default=35, min_value=0)
    credits = serializers.IntegerField(required=False, allow_null=True)
    isElective = serializers.BooleanField(required=False, default=False)


class BatchSubjectSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    batchId = serializers.UUIDField(source="batch_id", read_only=True)
    subjectId = serializers.UUIDField(source="subject_id", read_only=True)
    academicPeriodId = serializers.UUIDField(source="academic_period_id", read_only=True)
    isRequired = serializers.BooleanField(source="is_required", read_only=True)
    version = serializers.IntegerField(read_only=True)


class CreateBatchSubjectSerializer(serializers.Serializer):
    batchId = serializers.UUIDField()
    subjectId = serializers.UUIDField()
    academicPeriodId = serializers.UUIDField()
    isRequired = serializers.BooleanField(required=False, default=True)


class UpdateBatchSubjectSerializer(serializers.Serializer):
    isRequired = serializers.BooleanField(required=False)
    version = serializers.IntegerField(required=False)


class BatchFacultySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    batchSubjectId = serializers.UUIDField(source="batch_subject_id", read_only=True)
    facultyId = serializers.UUIDField(source="faculty_id", read_only=True)
    role = serializers.CharField(read_only=True)
    assignedAt = serializers.DateField(source="assigned_at", read_only=True)
    endedAt = serializers.DateField(source="ended_at", read_only=True, allow_null=True)
    version = serializers.IntegerField(read_only=True)


class CreateBatchFacultySerializer(serializers.Serializer):
    batchSubjectId = serializers.UUIDField()
    facultyId = serializers.UUIDField()
    role = serializers.ChoiceField(choices=BatchFacultyRole.values, required=False,
                                   default=BatchFacultyRole.PRIMARY)
    assignedAt = serializers.DateField()
    endedAt = serializers.DateField(required=False, allow_null=True)


class UpdateBatchFacultySerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=BatchFacultyRole.values, required=False)
    endedAt = serializers.DateField(required=False, allow_null=True)
    version = serializers.IntegerField(required=False)
