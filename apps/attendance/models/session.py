"""AttendanceSession — a class-period (session mode) or a whole day (day mode)."""

from django.db import models

from apps.attendance.enums import SessionStatus
from apps.core.models import BaseModel
from apps.organizations.enums import AttendanceMode


class AttendanceSession(BaseModel):
    """
    A unit of attendance for a batch on a date.

    - session mode: tied to a batch_subject + period_slot (one per class period)
    - day mode: batch_subject and period_slot are null (one per batch per day)

    `batch` is always set so scoping, roster, and the frozen-year guard work the
    same way in both modes.

    Note (PRD partitioning): in production this is RANGE-partitioned on created_at
    monthly; not needed at Phase-1 scale.
    """

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="attendance_sessions"
    )
    batch = models.ForeignKey(
        "academics.Batch", on_delete=models.CASCADE, related_name="attendance_sessions"
    )
    mode = models.CharField(max_length=10, choices=AttendanceMode.choices, default=AttendanceMode.SESSION)

    # Session mode only (null in day mode):
    batch_subject = models.ForeignKey(
        "academics.BatchSubject", on_delete=models.CASCADE, null=True, blank=True,
        related_name="attendance_sessions",
    )
    period_slot = models.ForeignKey(
        "academics.PeriodSlot", on_delete=models.PROTECT, null=True, blank=True,
        related_name="attendance_sessions",
    )

    date = models.DateField(db_index=True)
    faculty = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="taken_sessions", limit_choices_to={"role": "faculty"},
    )
    status = models.CharField(max_length=15, choices=SessionStatus.choices, default=SessionStatus.SCHEDULED)
    is_exam_day = models.BooleanField(
        default=False, help_text="If true and tenant excludes exam days, this session is dropped from %."
    )

    class Meta:
        db_table = "attendance_session"
        verbose_name = "Attendance Session"
        verbose_name_plural = "Attendance Sessions"
        constraints = [
            # Session mode: one per class/slot/day.
            models.UniqueConstraint(
                fields=["batch_subject", "date", "period_slot"],
                condition=models.Q(batch_subject__isnull=False),
                name="unique_session_per_class_slot_day",
            ),
            # Day mode: one per batch/day.
            models.UniqueConstraint(
                fields=["batch", "date"],
                condition=models.Q(batch_subject__isnull=True),
                name="unique_day_session_per_batch",
            ),
        ]
        indexes = [
            models.Index(fields=["branch", "date"]),
            models.Index(fields=["faculty", "date"]),
        ]

    def __str__(self):
        if self.mode == AttendanceMode.DAY:
            return f"Day {self.batch_id} @ {self.date}"
        return f"{self.batch_subject_id} @ {self.date} / slot {self.period_slot_id}"
