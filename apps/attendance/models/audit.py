"""AttendanceAudit — immutable trail for corrections, late marks, geo failures."""

from django.db import models

from apps.attendance.enums import AttendanceStatus, AuditType
from apps.core.models import BaseModel


class AttendanceAudit(BaseModel):
    """
    Append-only audit entry (never updated/deleted) for:
      - retroactive edits (F-107 / EC-ATT-04) — keeps the original status diff
      - late markings (F-108 / EC-ATT-02)
      - geo-fence failures (F-103 / EC-ATT-03)
    """

    record = models.ForeignKey(
        "attendance.AttendanceRecord", on_delete=models.CASCADE, related_name="audits"
    )
    audit_type = models.CharField(max_length=20, choices=AuditType.choices, db_index=True)
    original_status = models.CharField(max_length=15, choices=AttendanceStatus.choices, null=True, blank=True)
    new_status = models.CharField(max_length=15, choices=AttendanceStatus.choices, null=True, blank=True)
    actor = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="attendance_audits"
    )
    reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "attendance_audit"
        verbose_name = "Attendance Audit"
        verbose_name_plural = "Attendance Audits"
        indexes = [models.Index(fields=["record", "created_at"])]

    def __str__(self):
        return f"{self.audit_type} on {self.record_id}"
