"""
TenantSettings — per-tenant configurable labels and thresholds.

Distinct from Tenant.settings (free-form JSONB feature toggles): these are
typed, queryable settings returned by GET /tenant-config/ and used across the UI.
"""

from django.db import models

from apps.core.models import BaseModel
from apps.organizations.enums import AttendanceMode


class TenantSettings(BaseModel):
    """One row per tenant; holds login labels, attendance/exam thresholds, notification prefs."""

    tenant = models.OneToOneField(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="tenant_settings",
    )

    # Login page labels (configurable per PRD)
    student_id_label = models.CharField(
        max_length=50,
        default="Roll Number",
        help_text='Label shown on login page for student ID. e.g. "Roll Number", "Admission Number".',
    )
    faculty_id_label = models.CharField(
        max_length=50,
        default="Employee ID",
        help_text='Label shown on login page for faculty ID. e.g. "Employee ID", "Staff Code".',
    )

    # ── Auto-generated ID formats ────────────────────────────────────────────
    # Templates rendered by accounts.id_generation.generate_user_id().
    # Tokens: {BRANCH} branch code · {YEAR} 4-digit start year · {YY} 2-digit ·
    #         {ROLE} STU/FAC · {SEQ} zero-padded running number.
    student_id_format = models.CharField(
        max_length=64,
        default="{BRANCH}/{YEAR}/{SEQ}",
        help_text="Template for student admission/roll IDs. Tokens: {BRANCH} {YEAR} {YY} {ROLE} {SEQ}.",
    )
    faculty_id_format = models.CharField(
        max_length=64,
        default="{BRANCH}-FAC-{SEQ}",
        help_text="Template for faculty employee IDs. Tokens: {BRANCH} {YEAR} {YY} {ROLE} {SEQ}.",
    )
    student_id_seq_width = models.PositiveSmallIntegerField(
        default=5, help_text="Zero-padding width for the {SEQ} token in student IDs.",
    )
    faculty_id_seq_width = models.PositiveSmallIntegerField(
        default=4, help_text="Zero-padding width for the {SEQ} token in faculty IDs.",
    )
    student_id_reset_yearly = models.BooleanField(
        default=True,
        help_text="Reset the student sequence each academic year (vs. run continuously).",
    )

    # Attendance thresholds
    attendance_threshold_percent = models.PositiveSmallIntegerField(
        default=75,
        help_text="Minimum attendance % required. Default: 75%.",
    )
    exam_day_counts_toward_attendance = models.BooleanField(default=True)
    # Day-wise (one mark/student/day) vs session-wise (one mark/class period).
    attendance_mode = models.CharField(
        max_length=10, choices=AttendanceMode.choices, default=AttendanceMode.SESSION,
    )

    # Examination
    grace_marks_enabled = models.BooleanField(default=False)
    absent_exam_affects_gpa = models.BooleanField(default=False)

    # Notifications
    sms_enabled = models.BooleanField(default=True)
    email_enabled = models.BooleanField(default=True)
    fee_reminder_days = models.JSONField(
        default=list,
        blank=True,
        help_text="Days before due date to send fee reminders, e.g. [7, 5, 3, 1].",
    )

    class Meta:
        db_table = "organizations_tenant_settings"
        verbose_name = "Tenant Settings"
        verbose_name_plural = "Tenant Settings"

    def __str__(self):
        return f"Settings for {self.tenant.name}"
