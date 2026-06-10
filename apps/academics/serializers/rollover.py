"""Serializers — Academic year rollover."""

from rest_framework import serializers


class RolloverExecuteSerializer(serializers.Serializer):
    expectedVersion = serializers.IntegerField()
    branchId = serializers.UUIDField(required=False)


class RolloverPreviewSerializer(serializers.Serializer):
    branchId = serializers.UUIDField(required=False)
