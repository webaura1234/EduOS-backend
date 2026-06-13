"""Analytics enums."""

from django.db import models


class ReportStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    RUNNING = "running", "Running"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"
    TIMED_OUT = "timed_out", "Timed Out"


class ReportType(models.TextChoices):
    ATTENDANCE_MONTHLY = "attendance_monthly", "Attendance — Monthly"
    FEE_DEFAULTERS = "fee_defaulters", "Fees — Defaulters"
    FEE_COLLECTION = "fee_collection", "Fees — Collection"
    ADMISSION_FUNNEL = "admission_funnel", "Admissions — Funnel"
    HR_LEAVE_SUMMARY = "hr_leave_summary", "HR — Leave Summary"
    NAAC = "naac", "NAAC / NIRF"
