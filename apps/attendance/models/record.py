"""AttendanceRecord — one student's mark in a session."""

from django.db import models

from apps.attendance.enums import AttendanceStatus
from apps.core.models import BaseModel


class AttendanceRecord(BaseModel):
    """
    A student's attendance mark for a session.

    Student identity: attendance keys off admissions.StudentEnrollment (Stage 5,
    OD-1 Option A). The `student` field name is retained for continuity; it now points
    at the enrollment record, which mirrors the StudentProfile API via convenience
    properties (`.user`, `.current_batch`, `.academic_status`).
    """

    session = models.ForeignKey(
        "attendance.AttendanceSession", on_delete=models.CASCADE, related_name="records"
    )
    student = models.ForeignKey(
        "admissions.StudentEnrollment", on_delete=models.CASCADE, related_name="attendance_records"
    )
    status = models.CharField(max_length=15, choices=AttendanceStatus.choices, default=AttendanceStatus.PRESENT)

    # Geo (F-103) — store-and-flag; radius enforcement is a later config.
    geo_lat = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geo_lng = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)

    marked_at = models.DateTimeField()
    marked_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="marked_records"
    )
    late_mark = models.BooleanField(default=False, help_text="Marked >2h after slot end (F-108).")

    # EC-ATT-06: idempotent offline sync. Unique per (session, student).
    idempotency_key = models.CharField(max_length=120, unique=True, db_index=True)

    class Meta:
        db_table = "attendance_record"
        verbose_name = "Attendance Record"
        verbose_name_plural = "Attendance Records"
        constraints = [
            models.UniqueConstraint(fields=["session", "student"], name="unique_record_per_session_student"),
        ]
        indexes = [
            models.Index(fields=["session"]),
            models.Index(fields=["student", "marked_at"]),
        ]

    def __str__(self):
        return f"{self.student_id} — {self.status} ({self.session_id})"
