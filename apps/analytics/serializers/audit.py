"""Serializers — audit log + support mode (camelCase, read-only)."""

from rest_framework import serializers


class AuditLogSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    actorUserId = serializers.UUIDField(source="actor_user_id", read_only=True, allow_null=True)
    action = serializers.CharField(read_only=True)
    entityType = serializers.CharField(source="entity_type", read_only=True)
    entityId = serializers.CharField(source="entity_id", read_only=True)
    diff = serializers.JSONField(read_only=True)
    ipAddress = serializers.CharField(source="ip_address", read_only=True, allow_null=True)
    correlationId = serializers.CharField(source="correlation_id", read_only=True)
    rowHash = serializers.CharField(source="row_hash", read_only=True)
    prevHash = serializers.CharField(source="prev_hash", read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)


class SupportModeLogSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    tenantId = serializers.UUIDField(source="tenant_id", read_only=True)
    platformOwnerId = serializers.UUIDField(source="platform_owner_id", read_only=True, allow_null=True)
    startedAt = serializers.DateTimeField(source="started_at", read_only=True)
    endedAt = serializers.DateTimeField(source="ended_at", read_only=True, allow_null=True)
    reason = serializers.CharField(read_only=True)
    readOnly = serializers.BooleanField(source="read_only", read_only=True)
