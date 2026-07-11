"""Notification template registry — title/message patterns and required variables."""

from apps.communications.enums import NotificationPriority

TEMPLATES: dict[str, dict] = {
    "fee.due_reminder": {
        "title": "Fee due in {days_until_due} days",
        "message": "{student_name}, ₹{amount_due} is due on {due_date}.",
        "priority": NotificationPriority.NORMAL,
        "required": {"student_name", "amount_due", "due_date", "days_until_due"},
    },
    "fee.due_today": {
        "title": "Fee due today",
        "message": "{student_name}, ₹{amount_due} is due today ({due_date}).",
        "priority": NotificationPriority.HIGH,
        "required": {"student_name", "amount_due", "due_date"},
    },
    "fee.overdue": {
        "title": "Fee overdue",
        "message": "{student_name}, ₹{amount_due} was due on {due_date} ({days_overdue} days overdue).",
        "priority": NotificationPriority.CRITICAL,
        "required": {"student_name", "amount_due", "due_date", "days_overdue"},
    },
    "fee.payment_received": {
        "title": "Payment received",
        "message": "{student_name}, we received ₹{amount_paid}. Ref: {receipt_ref}.",
        "priority": NotificationPriority.NORMAL,
        "required": {"student_name", "amount_paid", "receipt_ref"},
    },
    "attendance.absent": {
        "title": "Marked absent",
        "message": "{student_name} was marked absent on {date} ({class_label}).",
        "priority": NotificationPriority.HIGH,
        "required": {"student_name", "date", "class_label"},
    },
    "attendance.shortage": {
        "title": "Attendance below minimum",
        "message": "{student_name}, attendance is {attendance_percent}% (minimum {threshold_percent}%).",
        "priority": NotificationPriority.CRITICAL,
        "required": {"student_name", "attendance_percent", "threshold_percent"},
    },
    "examination.results_published": {
        "title": "Results published",
        "message": "{student_name}, results for {exam_name} are now available.",
        "priority": NotificationPriority.HIGH,
        "required": {"student_name", "exam_name", "exam_id"},
    },
    "admissions.status_updated": {
        "title": "Application status updated",
        "message": "{applicant_name} (App #{application_number}): status is now {new_status}.",
        "priority": NotificationPriority.NORMAL,
        "required": {"applicant_name", "application_number", "new_status", "application_id"},
    },
    "announcement.published": {
        "title": "{title}",
        "message": "{body_preview}",
        "priority": NotificationPriority.NORMAL,
        "required": {"title", "announcement_id", "body_preview"},
    },
}
