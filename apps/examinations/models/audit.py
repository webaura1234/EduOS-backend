"""MarksAudit — immutable trail for deadline and conflict-of-interest overrides."""

from django.db import models

from apps.core.models import BaseModel
from apps.examinations.enums import MarksAuditType


class MarksAudit(BaseModel):
    """Append-only audit for marks entry overrides (EC-FORM-05, EC-GUARD-02)."""

    marks_entry = models.ForeignKey(
        "examinations.MarksEntry",
        on_delete=models.CASCADE,
        related_name="audits",
    )
    audit_type = models.CharField(max_length=25, choices=MarksAuditType.choices, db_index=True)
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="marks_audits",
    )
    reason = models.TextField(blank=True, default="")
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "examinations_marks_audit"
        verbose_name = "Marks Audit"
        verbose_name_plural = "Marks Audits"
        indexes = [models.Index(fields=["marks_entry", "created_at"])]

    def __str__(self):
        return f"{self.audit_type} on {self.marks_entry_id}"
