"""Serializers — report exports (camelCase)."""

from rest_framework import serializers

from apps.analytics.enums import ReportType


class ReportExportSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    reportType = serializers.CharField(source="report_type", read_only=True)
    status = serializers.CharField(read_only=True)
    rowCount = serializers.IntegerField(source="row_count", read_only=True)
    snapshot = serializers.JSONField(read_only=True)
    fileKey = serializers.CharField(source="file_key", read_only=True)
    downloadUrl = serializers.CharField(source="download_url", read_only=True)
    expiresAt = serializers.DateTimeField(source="expires_at", read_only=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)


class CreateReportSerializer(serializers.Serializer):
    reportType = serializers.ChoiceField(choices=ReportType.values)
    params = serializers.JSONField(required=False, default=dict)
