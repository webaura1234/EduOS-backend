"""Saved report filter presets per user (v1)."""

from django.db import models

from apps.analytics.enums import ReportType
from apps.core.models import BaseModel


class SavedReportFilter(BaseModel):
    """A named filter preset for a catalog report."""

    tenant = models.ForeignKey(
        "organizations.Tenant", on_delete=models.CASCADE, related_name="saved_report_filters"
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="saved_report_filters"
    )
    report_type = models.CharField(max_length=30, choices=ReportType.choices)
    name = models.CharField(max_length=120)
    params = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "analytics_saved_report_filter"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "user", "report_type", "name"],
                name="unique_saved_filter_name_per_user_report",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "user", "report_type"]),
        ]

    def __str__(self):
        return f"SavedReportFilter({self.report_type}, {self.name})"
