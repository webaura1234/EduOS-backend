"""Notification inbox API serializers."""

from rest_framework import serializers


class NotificationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    category = serializers.CharField(read_only=True)
    type = serializers.CharField(source="notification_type", read_only=True)
    priority = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    message = serializers.CharField(read_only=True)
    actionUrl = serializers.CharField(source="action_url", read_only=True)
    relatedEntityType = serializers.CharField(source="related_entity_type", read_only=True)
    relatedEntityId = serializers.UUIDField(source="related_entity_id", read_only=True)
    read = serializers.SerializerMethodField()
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    readAt = serializers.DateTimeField(source="read_at", read_only=True)
    expiresAt = serializers.DateTimeField(source="expires_at", read_only=True)

    def get_read(self, obj) -> bool:
        return obj.read_at is not None
