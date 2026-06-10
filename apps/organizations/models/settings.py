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

    class Meta:
        db_table = "organizations_tenant_settings"
        verbose_name = "Tenant Settings"
        verbose_name_plural = "Tenant Settings"

    def __str__(self):
        return f"Settings for {self.tenant.name}"
