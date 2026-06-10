"""
Enumerations for the organizations app.

Centralised here so models, serializers, and services share one source of truth.
"""

from django.db import models


class InstitutionType(models.TextChoices):
    SCHOOL = "school", "School"
    COLLEGE = "college", "College"


class InstitutionStatus(models.TextChoices):
    TRIAL = "trial", "Trial"
    ACTIVE = "active", "Active"
    SUSPENDED = "suspended", "Suspended"
    DEACTIVATED = "deactivated", "Deactivated"
    OFFBOARDING = "offboarding", "Offboarding"


class PlanType(models.TextChoices):
    STARTER = "starter", "Starter"
    GROWTH = "growth", "Growth"
    ENTERPRISE = "enterprise", "Enterprise"


class BillingStatus(models.TextChoices):
    TRIAL = "trial", "Trial"
    PAID = "paid", "Paid"
    OVERDUE = "overdue", "Overdue"
    CANCELLED = "cancelled", "Cancelled"


class QuotaResource(models.TextChoices):
    """Metered resources tracked per tenant (TenantQuota)."""
    STUDENTS = "students", "Students"
    STORAGE_BYTES = "storage_bytes", "Storage (bytes)"
    SMS_COUNT = "sms_count", "SMS count"
    AI_TOKENS = "ai_tokens", "AI tokens"
    API_CALLS = "api_calls", "API calls"


class QuotaPeriod(models.TextChoices):
    """Accounting window for a quota counter."""
    MONTH = "month", "Per month"
    TOTAL = "total", "Lifetime total"


class AttendanceMode(models.TextChoices):
    """How a tenant takes attendance."""
    DAY = "day", "Day-wise (one mark per student per day)"
    SESSION = "session", "Session-wise (one mark per class period)"
