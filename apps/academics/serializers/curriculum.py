"""Serializers — Subject (camelCase I/O)."""

from rest_framework import serializers

from apps.academics.models import SubjectType


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
