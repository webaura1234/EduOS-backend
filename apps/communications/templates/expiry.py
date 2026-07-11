"""Per-type expiration rules for notifications."""

import calendar
from datetime import date, datetime, timedelta

from django.utils import timezone


def compute_expires_at(
    notification_type: str,
    *,
    created_at: datetime | None = None,
    due_date: date | None = None,
) -> datetime | None:
    """Return expires_at for a notification type, or None for permanent."""
    now = created_at or timezone.now()

    if notification_type in ("fee.due_reminder", "fee.due_today", "fee.overdue"):
        if due_date:
            return timezone.make_aware(
                datetime.combine(due_date + timedelta(days=7), datetime.min.time())
            )
        return now + timedelta(days=14)

    if notification_type == "fee.payment_received":
        return now + timedelta(days=30)

    if notification_type == "attendance.absent":
        return now + timedelta(days=7)

    if notification_type == "attendance.shortage":
        today = timezone.localdate()
        last_day = calendar.monthrange(today.year, today.month)[1]
        end_of_month = date(today.year, today.month, last_day)
        return timezone.make_aware(
            datetime.combine(end_of_month + timedelta(days=7), datetime.min.time())
        )

    if notification_type in (
        "examination.results_published",
        "admissions.status_updated",
    ):
        return None

    if notification_type == "announcement.published":
        return now + timedelta(days=90)

    return now + timedelta(days=30)
