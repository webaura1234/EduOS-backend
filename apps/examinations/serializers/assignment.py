"""Serializers — assignments and submissions (camelCase)."""

from rest_framework import serializers


class AssignmentSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    title = serializers.CharField()
    description = serializers.CharField()
    classSectionId = serializers.CharField()
    classLabel = serializers.CharField()
    subjectId = serializers.CharField()
    subjectName = serializers.CharField()
    dueAt = serializers.CharField()
    maxMarks = serializers.FloatField()
    status = serializers.CharField()
    createdAt = serializers.CharField()
    createdByUserId = serializers.CharField()


class SubmissionSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    assignmentId = serializers.UUIDField()
    studentId = serializers.UUIDField()
    studentName = serializers.CharField()
    submittedAt = serializers.CharField()
    attachmentName = serializers.CharField()
    gradedMarks = serializers.FloatField(allow_null=True)
    similarityPercent = serializers.FloatField()
    similarityStatus = serializers.CharField()
    submissionStatus = serializers.CharField()


class CreateAssignmentSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=200)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    classSectionId = serializers.UUIDField()
    subjectId = serializers.UUIDField()
    dueAt = serializers.DateTimeField()
    maxMarks = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
    academicPeriodId = serializers.UUIDField(required=False, allow_null=True)


class SubmitAssignmentSerializer(serializers.Serializer):
    fileName = serializers.CharField(max_length=255)
    fileContent = serializers.CharField()


class GradeSubmissionSerializer(serializers.Serializer):
    gradedMarks = serializers.DecimalField(max_digits=6, decimal_places=2, min_value=0)
