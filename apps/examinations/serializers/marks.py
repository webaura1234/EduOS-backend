"""Serializers — marks entry (camelCase)."""

from rest_framework import serializers


class MarksEntrySerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    examSlotId = serializers.CharField()
    studentId = serializers.UUIDField()
    studentName = serializers.CharField()
    classLabel = serializers.CharField()
    subjectName = serializers.CharField()
    marks = serializers.FloatField(allow_null=True)
    maxMarks = serializers.FloatField()
    isAbsent = serializers.BooleanField()
    marksStatus = serializers.CharField()
    version = serializers.IntegerField()
    updatedAt = serializers.CharField()


class RosterStudentSerializer(serializers.Serializer):
    studentId = serializers.UUIDField()
    studentName = serializers.CharField()
    classLabel = serializers.CharField()
    marks = serializers.FloatField(allow_null=True, required=False)
    isAbsent = serializers.BooleanField(required=False)
    marksStatus = serializers.CharField(required=False)
    marksEntryId = serializers.UUIDField(allow_null=True, required=False)
    version = serializers.IntegerField(allow_null=True, required=False)


class BulkMarksEntryInputSerializer(serializers.Serializer):
    studentId = serializers.UUIDField()
    marks = serializers.FloatField(allow_null=True, required=False)
    isAbsent = serializers.BooleanField(required=False, default=False)


class BulkSaveMarksSerializer(serializers.Serializer):
    entries = BulkMarksEntryInputSerializer(many=True)
    override = serializers.BooleanField(required=False, default=False)
    overrideReason = serializers.CharField(required=False, allow_blank=True, default="")


class PatchMarksSerializer(serializers.Serializer):
    marks = serializers.FloatField(allow_null=True, required=False)
    isAbsent = serializers.BooleanField(required=False, default=False)
    version = serializers.IntegerField()
    override = serializers.BooleanField(required=False, default=False)
    overrideReason = serializers.CharField(required=False, allow_blank=True, default="")


class SubmitMarksSerializer(serializers.Serializer):
    override = serializers.BooleanField(required=False, default=False)
    overrideReason = serializers.CharField(required=False, allow_blank=True, default="")
