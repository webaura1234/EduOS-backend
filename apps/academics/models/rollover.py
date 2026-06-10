"""Academic year rollover run tracking and undo snapshots."""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class RolloverRunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    COMPENSATED = "compensated", "Compensated"


class AcademicRolloverRun(BaseModel):
    """Tracks a rollover execution and stores undo snapshot (24h window)."""

    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="rollover_runs",
    )
    from_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="rollover_runs_from",
    )
    to_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="rollover_runs_to",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=15,
        choices=RolloverRunStatus.choices,
        default=RolloverRunStatus.PENDING,
        db_index=True,
    )
    snapshot = models.JSONField(default=dict, blank=True)
    preview_version = models.IntegerField(default=1)
    undo_expires_at = models.DateTimeField(null=True, blank=True)
    executed_at = models.DateTimeField(null=True, blank=True)
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="rollover_runs_executed",
    )
    error_message = models.TextField(blank=True, default="")

    class Meta:
        db_table = "academics_rollover_run"
        ordering = ["-created_at"]

    def __str__(self):
        return f"Rollover {self.branch.name} {self.from_year.name} → {self.to_year_id}"
