"""Student bulk-import job + saved column mappings."""

from django.db import models

from apps.core.models import BaseModel


class StudentImportMode(models.TextChoices):
    CREATE = "create", "Create new only"
    UPDATE = "update", "Update existing only"
    UPSERT = "upsert", "Create + update"


class StudentImportStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    VALIDATING = "validating", "Validating"
    RUNNING = "running", "Running"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"


class StudentImportJob(BaseModel):
    """One bulk student import run (file → validate → Celery apply)."""

    tenant = models.ForeignKey(
        "organizations.Tenant", on_delete=models.CASCADE, related_name="student_import_jobs"
    )
    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="student_import_jobs"
    )
    academic_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_import_jobs",
    )
    filename = models.CharField(max_length=255, blank=True, default="")
    mode = models.CharField(
        max_length=16, choices=StudentImportMode.choices, default=StudentImportMode.CREATE
    )
    status = models.CharField(
        max_length=16,
        choices=StudentImportStatus.choices,
        default=StudentImportStatus.QUEUED,
        db_index=True,
    )
    total_rows = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    # Stored upload + generated error report on S3 (or sandbox).
    file_key = models.CharField(max_length=512, blank=True, default="")
    error_report_key = models.CharField(max_length=512, blank=True, default="")
    # Canonical-key → source-header map used for this run.
    mapping = models.JSONField(default=dict, blank=True)
    # Cached validation / row payloads for the apply phase (capped).
    row_payload = models.JSONField(default=list, blank=True)
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    error = models.TextField(blank=True, default="")
    requested_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_import_jobs",
    )

    class Meta:
        db_table = "admissions_student_import_job"
        indexes = [
            models.Index(fields=["tenant", "branch", "status", "created_at"]),
        ]

    def __str__(self):
        return f"StudentImportJob({self.filename}, {self.status})"


class StudentImportMapping(BaseModel):
    """Saved column mapping profile for future imports."""

    tenant = models.ForeignKey(
        "organizations.Tenant", on_delete=models.CASCADE, related_name="student_import_mappings"
    )
    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="student_import_mappings"
    )
    name = models.CharField(max_length=120)
    mapping = models.JSONField(default=dict, blank=True)
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="student_import_mappings_updated",
    )

    class Meta:
        db_table = "admissions_student_import_mapping"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "branch", "name"],
                condition=models.Q(is_active=True),
                name="unique_active_student_import_mapping_name",
            )
        ]

    def __str__(self):
        return f"StudentImportMapping({self.name})"
