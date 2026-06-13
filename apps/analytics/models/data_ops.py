"""
Analytics — report exports (F-062/063/064/236).

  - ReportExport → a requested module report; small ones resolve inline (snapshot),
                   large ones run via a Celery task that uploads to S3 (signed URL).

DSAR DataExport / DataDeletion (EC-PRIV-*) are deferred to the Compliance/Operations stage.
"""

from django.db import models

from apps.analytics.enums import ReportStatus, ReportType
from apps.core.models import BaseModel


class ReportExport(BaseModel):
    """A report/export request with snapshot-at-request semantics (F-064)."""

    tenant = models.ForeignKey(
        "organizations.Tenant", on_delete=models.CASCADE, related_name="report_exports"
    )
    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="report_exports",
    )
    report_type = models.CharField(max_length=30, choices=ReportType.choices)
    params = models.JSONField(default=dict, blank=True)
    status = models.CharField(
        max_length=15, choices=ReportStatus.choices, default=ReportStatus.QUEUED, db_index=True
    )
    row_count = models.IntegerField(default=0)
    # Small reports store the frozen result here; large ones upload to S3 (file_key).
    snapshot = models.JSONField(default=dict, blank=True)
    file_key = models.CharField(max_length=512, blank=True, default="")
    download_url = models.CharField(max_length=1024, blank=True, default="")
    requested_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="report_requests",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "analytics_report_export"
        indexes = [models.Index(fields=["tenant", "status", "created_at"])]

    def __str__(self):
        return f"ReportExport({self.report_type}, {self.status})"
