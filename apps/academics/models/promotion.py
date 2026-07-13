"""Academic year promotion workspace — decision-only sessions (Phase 1)."""

from django.conf import settings
from django.db import models

from apps.core.models import BaseModel


class PromotionSessionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    APPROVED = "approved", "Approved"


class PromotionAction(models.TextChoices):
    PROMOTE = "promote", "Promote"
    RETAIN = "retain", "Retain"
    GRADUATE = "graduate", "Graduate"
    TRANSFER_OUT = "transfer_out", "Transfer Out"
    WITHDRAWN = "withdrawn", "Withdrawn"
    MANUAL_REVIEW = "manual_review", "Manual Review"
    PENDING = "pending", "Pending"


class PreparationStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not Started"
    IN_PROGRESS = "in_progress", "In Progress"
    LOCKED = "locked", "Locked"
    INVALID = "invalid", "Invalid"


class ExecutionReadiness(models.TextChoices):
    READY = "ready", "Ready"
    BLOCKED = "blocked", "Blocked"


class PreparationLogEvent(models.TextChoices):
    LOCK = "lock", "Lock"
    UNLOCK = "unlock", "Unlock"
    INVALIDATED = "invalidated", "Invalidated"
    EXECUTED = "executed", "Executed"


class PromotionExecutionStatus(models.TextChoices):
    NOT_STARTED = "not_started", "Not Started"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    PARTIAL = "partial", "Partial"
    FAILED = "failed", "Failed"


class ExecutionLogStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    SKIPPED = "skipped", "Skipped"


class AcademicPromotionSession(BaseModel):
    """In-progress or approved promotion decisions for a branch + source year."""

    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="promotion_sessions",
    )
    source_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="promotion_sessions_from",
    )
    target_year = models.ForeignKey(
        "academics.AcademicYear",
        on_delete=models.PROTECT,
        related_name="promotion_sessions_to",
    )
    status = models.CharField(
        max_length=10,
        choices=PromotionSessionStatus.choices,
        default=PromotionSessionStatus.DRAFT,
        db_index=True,
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_sessions_approved",
    )
    preparation_status = models.CharField(
        max_length=15,
        choices=PreparationStatus.choices,
        default=PreparationStatus.NOT_STARTED,
        db_index=True,
    )
    preparation_started_at = models.DateTimeField(null=True, blank=True)
    preparation_locked_at = models.DateTimeField(null=True, blank=True)
    preparation_locked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_sessions_locked",
    )
    validation_snapshot = models.JSONField(default=dict, blank=True)
    execution_preview_snapshot = models.JSONField(default=dict, blank=True)
    lock_fingerprint = models.JSONField(default=dict, blank=True)
    staleness_detected_at = models.DateTimeField(null=True, blank=True)
    execution_status = models.CharField(
        max_length=15,
        choices=PromotionExecutionStatus.choices,
        default=PromotionExecutionStatus.NOT_STARTED,
        db_index=True,
    )
    executed_at = models.DateTimeField(null=True, blank=True)
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_sessions_executed",
    )
    execution_report = models.JSONField(default=dict, blank=True)
    rollover_run = models.ForeignKey(
        "academics.AcademicRolloverRun",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_sessions",
    )

    class Meta:
        db_table = "academics_promotion_session"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "source_year"],
                condition=models.Q(status=PromotionSessionStatus.DRAFT),
                name="unique_draft_promotion_per_branch_source",
            ),
            models.UniqueConstraint(
                fields=["branch", "source_year"],
                condition=models.Q(status=PromotionSessionStatus.APPROVED),
                name="unique_approved_promotion_per_branch_source",
            ),
        ]

    def __str__(self):
        return f"Promotion {self.branch.name} {self.source_year.name} → {self.target_year.name}"


class AcademicPromotionDecision(BaseModel):
    """Per-student recommended and final promotion action within a session."""

    session = models.ForeignKey(
        AcademicPromotionSession,
        on_delete=models.CASCADE,
        related_name="decisions",
    )
    student_profile = models.ForeignKey(
        "accounts.StudentProfile",
        on_delete=models.CASCADE,
        related_name="promotion_decisions",
    )
    student_name = models.CharField(max_length=255)
    branch_id_snapshot = models.UUIDField(db_index=True)
    course_id = models.UUIDField(null=True, blank=True, db_index=True)
    course_name = models.CharField(max_length=120, blank=True, default="")
    batch_id = models.UUIDField(null=True, blank=True, db_index=True)
    section_name = models.CharField(max_length=50, blank=True, default="")
    recommended_action = models.CharField(max_length=20, choices=PromotionAction.choices)
    recommended_reason_code = models.CharField(max_length=64, blank=True, default="")
    recommended_reason_label = models.CharField(max_length=255, blank=True, default="")
    final_action = models.CharField(max_length=20, choices=PromotionAction.choices)
    is_overridden = models.BooleanField(default=False)
    override_reason = models.TextField(blank=True, default="")
    target_course_id = models.UUIDField(null=True, blank=True, db_index=True)
    target_course_name = models.CharField(max_length=120, blank=True, default="")
    target_batch_id = models.UUIDField(null=True, blank=True, db_index=True)
    target_section_name = models.CharField(max_length=50, blank=True, default="")
    execution_readiness = models.CharField(
        max_length=10,
        choices=ExecutionReadiness.choices,
        null=True,
        blank=True,
    )
    block_reasons = models.JSONField(default=list, blank=True)
    target_fee_structure_id = models.UUIDField(null=True, blank=True)
    target_fee_structure_name = models.CharField(max_length=150, blank=True, default="")

    class Meta:
        db_table = "academics_promotion_decision"
        constraints = [
            models.UniqueConstraint(
                fields=["session", "student_profile"],
                name="unique_decision_per_student_session",
            ),
        ]
        ordering = ["student_name"]

    def __str__(self):
        return f"{self.student_name} → {self.final_action}"


class AcademicPromotionOverrideLog(BaseModel):
    """Append-only audit of admin overrides within a promotion session."""

    session = models.ForeignKey(
        AcademicPromotionSession,
        on_delete=models.CASCADE,
        related_name="override_logs",
    )
    decision = models.ForeignKey(
        AcademicPromotionDecision,
        on_delete=models.CASCADE,
        related_name="override_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_override_logs",
    )
    from_action = models.CharField(max_length=20, choices=PromotionAction.choices)
    to_action = models.CharField(max_length=20, choices=PromotionAction.choices)
    reason = models.TextField()

    class Meta:
        db_table = "academics_promotion_override_log"
        ordering = ["created_at"]

    def __str__(self):
        return f"Override {self.from_action} → {self.to_action}"


class AcademicPromotionClassMapping(BaseModel):
    """Source class → destination class mapping for a promotion session."""

    session = models.ForeignKey(
        AcademicPromotionSession,
        on_delete=models.CASCADE,
        related_name="class_mappings",
    )
    source_course_id = models.UUIDField(db_index=True)
    source_course_name = models.CharField(max_length=120, blank=True, default="")
    target_course_id = models.UUIDField(db_index=True)
    target_course_name = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        db_table = "academics_promotion_class_mapping"
        constraints = [
            models.UniqueConstraint(
                fields=["session", "source_course_id"],
                name="unique_class_mapping_per_session_source",
            ),
        ]

    def __str__(self):
        return f"{self.source_course_name} → {self.target_course_name}"


class AcademicPromotionPreparationLog(BaseModel):
    """Append-only log of preparation lock/unlock/invalidation events."""

    session = models.ForeignKey(
        AcademicPromotionSession,
        on_delete=models.CASCADE,
        related_name="preparation_logs",
    )
    event = models.CharField(max_length=15, choices=PreparationLogEvent.choices)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_preparation_logs",
    )
    reason = models.TextField(blank=True, default="")
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "academics_promotion_preparation_log"
        ordering = ["created_at"]


class AcademicPromotionExecutionRun(BaseModel):
    """Tracks a promotion execution attempt with live progress."""

    session = models.ForeignKey(
        AcademicPromotionSession,
        on_delete=models.CASCADE,
        related_name="execution_runs",
    )
    status = models.CharField(
        max_length=15,
        choices=PromotionExecutionStatus.choices,
        default=PromotionExecutionStatus.RUNNING,
        db_index=True,
    )
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    error_message = models.TextField(blank=True, default="")
    student_total = models.PositiveIntegerField(default=0)
    processed_count = models.PositiveIntegerField(default=0)
    current_decision_id = models.UUIDField(null=True, blank=True)
    current_student_name = models.CharField(max_length=255, blank=True, default="")
    estimated_duration_ms = models.PositiveIntegerField(default=0)
    estimated_remaining_ms = models.PositiveIntegerField(default=0)
    promoted_count = models.PositiveIntegerField(default=0)
    retained_count = models.PositiveIntegerField(default=0)
    graduated_count = models.PositiveIntegerField(default=0)
    transferred_count = models.PositiveIntegerField(default=0)
    withdrawn_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    fee_assignments_created = models.PositiveIntegerField(default=0)
    opening_balances_carried = models.PositiveIntegerField(default=0)
    executed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promotion_execution_runs",
    )

    class Meta:
        db_table = "academics_promotion_execution_run"
        ordering = ["-started_at"]


class AcademicPromotionExecutionLog(BaseModel):
    """Per-student promotion execution audit row."""

    run = models.ForeignKey(
        AcademicPromotionExecutionRun,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    decision = models.ForeignKey(
        AcademicPromotionDecision,
        on_delete=models.CASCADE,
        related_name="execution_logs",
    )
    action = models.CharField(max_length=20, choices=PromotionAction.choices)
    status = models.CharField(max_length=10, choices=ExecutionLogStatus.choices)
    prior_enrollment_id = models.UUIDField(null=True, blank=True)
    new_enrollment_id = models.UUIDField(null=True, blank=True)
    fee_assignment_id = models.UUIDField(null=True, blank=True)
    opening_balance_paise = models.BigIntegerField(default=0)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        db_table = "academics_promotion_execution_log"
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["run", "decision"],
                name="unique_execution_log_per_run_decision",
            ),
        ]
