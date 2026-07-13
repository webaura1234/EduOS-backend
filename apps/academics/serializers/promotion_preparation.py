"""Serializers — Promotion preparation (Phase 2)."""

from rest_framework import serializers


class ClassMappingUpdateSerializer(serializers.Serializer):
    sourceCourseId = serializers.UUIDField()
    sourceCourseName = serializers.CharField(required=False, allow_blank=True)
    targetCourseId = serializers.UUIDField()


class ClassMappingsPatchSerializer(serializers.Serializer):
    mappings = ClassMappingUpdateSerializer(many=True)


class SectionAssignmentSerializer(serializers.Serializer):
    decisionId = serializers.UUIDField()
    targetBatchId = serializers.UUIDField()


class SectionMappingsPatchSerializer(serializers.Serializer):
    assignments = SectionAssignmentSerializer(many=True)


class PreparationUnlockSerializer(serializers.Serializer):
    reason = serializers.CharField(min_length=10, max_length=2000)


class BlockedStudentsQuerySerializer(serializers.Serializer):
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    pageSize = serializers.IntegerField(required=False, default=50, min_value=1, max_value=200)
