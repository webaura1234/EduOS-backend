"""Communications enums — notification categories, types, priorities."""

from django.db import models


class NotificationCategory(models.TextChoices):
    ANNOUNCEMENT = "announcement", "Announcement"
    ATTENDANCE = "attendance", "Attendance"
    FEES = "fees", "Fees"
    EXAMINATION = "examination", "Examination"
    ADMISSIONS = "admissions", "Admissions"
    ACADEMICS = "academics", "Academics"


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
    "academics.promotion_completed",
    "academics.promotion_retained",
    "academics.promotion_graduated",
    "academics.promotion_transferred",
    "academics.promotion_withdrawn",
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
    "academics.promotion_completed": NotificationCategory.ACADEMICS,
    "academics.promotion_retained": NotificationCategory.ACADEMICS,
    "academics.promotion_graduated": NotificationCategory.ACADEMICS,
    "academics.promotion_transferred": NotificationCategory.ACADEMICS,
    "academics.promotion_withdrawn": NotificationCategory.ACADEMICS,
}
