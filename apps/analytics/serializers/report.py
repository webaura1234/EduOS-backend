"""Serializers — report exports (camelCase)."""

from rest_framework import serializers

from apps.analytics.enums import ReportType


class ReportExportSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    reportType = serializers.CharField(source="report_type", read_only=True)
    module = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    rowCount = serializers.IntegerField(source="row_count", read_only=True)
    snapshot = serializers.JSONField(read_only=True)
    fileKey = serializers.CharField(source="file_key", read_only=True)
    downloadUrl = serializers.CharField(source="download_url", read_only=True)
    format = serializers.CharField(read_only=True)
    expiresAt = serializers.DateTimeField(source="expires_at", read_only=True, allow_null=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)
    error = serializers.CharField(read_only=True)


class CreateReportSerializer(serializers.Serializer):
    reportType = serializers.ChoiceField(choices=ReportType.values)
    params = serializers.JSONField(required=False, default=dict)
    branchId = serializers.UUIDField(required=False, allow_null=True)


class PreviewReportSerializer(serializers.Serializer):
    reportType = serializers.ChoiceField(choices=ReportType.values)
    params = serializers.JSONField(required=False, default=dict)
    branchId = serializers.UUIDField(required=False, allow_null=True)
    page = serializers.IntegerField(required=False, default=1, min_value=1)
    pageSize = serializers.IntegerField(required=False, default=50, min_value=1, max_value=200)
    search = serializers.CharField(required=False, default="", allow_blank=True)
    sortKey = serializers.CharField(required=False, default="", allow_blank=True)
    sortDir = serializers.ChoiceField(choices=["asc", "desc"], required=False, default="asc")


class CreateSavedFilterSerializer(serializers.Serializer):
    reportType = serializers.ChoiceField(choices=ReportType.values)
    name = serializers.CharField(max_length=120)
    params = serializers.JSONField(required=False, default=dict)


class SavedReportFilterSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    reportType = serializers.CharField(source="report_type", read_only=True)
    name = serializers.CharField(read_only=True)
    params = serializers.JSONField(read_only=True)
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
