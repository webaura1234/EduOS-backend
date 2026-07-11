"""Communications enums — notification categories, types, priorities."""

from django.db import models


class NotificationCategory(models.TextChoices):
    ANNOUNCEMENT = "announcement", "Announcement"
    ATTENDANCE = "attendance", "Attendance"
    FEES = "fees", "Fees"
    EXAMINATION = "examination", "Examination"
    ADMISSIONS = "admissions", "Admissions"


class NotificationPriority(models.TextChoices):
    LOW = "low", "Low"
    NORMAL = "normal", "Normal"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


# Stable type keys used by templates and triggers.
NOTIFICATION_TYPES = (
    "fee.due_reminder",
    "fee.due_today",
    "fee.overdue",
    "fee.payment_received",
    "attendance.absent",
    "attendance.shortage",
    "examination.results_published",
    "admissions.status_updated",
    "announcement.published",
)

TYPE_TO_CATEGORY = {
    "fee.due_reminder": NotificationCategory.FEES,
    "fee.due_today": NotificationCategory.FEES,
    "fee.overdue": NotificationCategory.FEES,
    "fee.payment_received": NotificationCategory.FEES,
    "attendance.absent": NotificationCategory.ATTENDANCE,
    "attendance.shortage": NotificationCategory.ATTENDANCE,
    "examination.results_published": NotificationCategory.EXAMINATION,
    "admissions.status_updated": NotificationCategory.ADMISSIONS,
    "announcement.published": NotificationCategory.ANNOUNCEMENT,
}
