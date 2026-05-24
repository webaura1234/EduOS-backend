"""
Organizations models — Tenant (Institution) and Branch.

Every multi-tenant data record in EduOS is scoped to a Tenant + Branch.
The Tenant is the root of all data isolation.
"""

import uuid

from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

from apps.core.models import BaseModel


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


subdomain_validator = RegexValidator(
    regex=r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$",
    message="Subdomain must be lowercase alphanumeric with hyphens (e.g. greenfield-academy).",
)


class Tenant(BaseModel):
    """
    Institution — the root tenant entity.

    Each school or college that subscribes to EduOS gets one Tenant row.
    All data (users, students, fees, exams) is scoped under a Tenant.

    Subdomain is globally unique and forms the login URL:
      e.g. greenfield.eduos.app
    """

    name = models.CharField(max_length=255)
    subdomain = models.CharField(
        max_length=63,
        unique=True,
        validators=[subdomain_validator],
        db_index=True,
    )
    institution_type = models.CharField(
        max_length=10,
        choices=InstitutionType.choices,
        default=InstitutionType.SCHOOL,
    )

    # Branding
    logo_s3_key = models.CharField(max_length=500, blank=True, default="")

    # Contact / Address
    address_line1 = models.CharField(max_length=255, blank=True, default="")
    address_line2 = models.CharField(max_length=255, blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="", db_index=True)
    state = models.CharField(max_length=100, blank=True, default="")
    country = models.CharField(max_length=100, blank=True, default="India")
    postal_code = models.CharField(max_length=20, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    website = models.URLField(blank=True, default="")

    # Localization
    timezone = models.CharField(max_length=50, default="Asia/Kolkata")

    # Lifecycle
    status = models.CharField(
        max_length=20,
        choices=InstitutionStatus.choices,
        default=InstitutionStatus.TRIAL,
        db_index=True,
    )
    activated_at = models.DateTimeField(null=True, blank=True)
    deactivated_at = models.DateTimeField(null=True, blank=True)

    # Features
    # For schools: always true. For colleges: admin can toggle.
    parent_access_enabled = models.BooleanField(default=True)
    mfa_enforced = models.BooleanField(default=False)

    # Tax / Legal
    gstin = models.CharField(max_length=15, blank=True, null=True)

    # Flexible feature flags and branding stored as JSON
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "organizations_tenant"
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"

    def __str__(self):
        return f"{self.name} ({self.subdomain})"

    @property
    def is_school(self):
        return self.institution_type == InstitutionType.SCHOOL

    @property
    def is_college(self):
        return self.institution_type == InstitutionType.COLLEGE

    @property
    def has_active_status(self):
        """True when institution lifecycle status is active (not soft-delete is_active)."""
        return self.status == InstitutionStatus.ACTIVE


class Branch(BaseModel):
    """
    A physical campus / location within a Tenant.

    Every operational record (user, student, attendance, fee) is scoped
    to a Branch. Super Admins can view all branches; Admins are typically
    scoped to one branch.

    Every Tenant must have at least one Branch (created automatically
    when the Tenant is onboarded — usually named "Main Campus").
    """

    tenant = models.ForeignKey(
        Tenant,
        on_delete=models.CASCADE,
        related_name="branches",
    )
    name = models.CharField(max_length=255)
    code = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Short code for reports (e.g. MC, NC).",
    )
    is_primary = models.BooleanField(
        default=False,
        help_text="True for the default campus created at tenant onboarding.",
    )

    # Address (may differ from Tenant address for multi-campus)
    address = models.TextField(blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    postal_code = models.CharField(max_length=20, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")

    # Localization — inherits from Tenant if null
    timezone = models.CharField(max_length=50, blank=True, null=True)

    # Academic calendar config
    academic_year_start_month = models.PositiveSmallIntegerField(
        default=4,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Month (1-12) when the academic year starts. Default: April.",
    )

    class Meta:
        db_table = "organizations_branch"
        verbose_name = "Branch"
        verbose_name_plural = "Branches"
        unique_together = [("tenant", "name")]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "code"],
                condition=models.Q(code__gt=""),
                name="unique_branch_code_per_tenant",
            ),
        ]

    def __str__(self):
        return f"{self.tenant.name} — {self.name}"

    @property
    def effective_timezone(self):
        return self.timezone or self.tenant.timezone


class TenantSettings(BaseModel):
    """
    Per-tenant configurable settings.

    Stores labels and thresholds that vary by institution but are
    not feature flags (those live in Tenant.settings JSONB).

    These settings are returned by GET /tenant-config/ and used
    on the login page and throughout the UI.
    """

    tenant = models.OneToOneField(
        Tenant,
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


class PlanSubscription(BaseModel):
    """
    Billing plan for a Tenant. One subscription per tenant.
    Controls feature limits and quota enforcement.
    """

    tenant = models.OneToOneField(
        Tenant,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    plan = models.CharField(
        max_length=20,
        choices=PlanType.choices,
        default=PlanType.STARTER,
    )
    billing_status = models.CharField(
        max_length=20,
        choices=BillingStatus.choices,
        default=BillingStatus.TRIAL,
    )

    # Limits
    student_limit = models.PositiveIntegerField(default=200)
    storage_limit_gb = models.PositiveIntegerField(default=10)
    sms_quota_per_month = models.PositiveIntegerField(default=500)
    ai_token_quota_per_month = models.PositiveIntegerField(default=10000)
    api_rpm_limit = models.PositiveIntegerField(default=100)

    valid_until = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "organizations_plan_subscription"
        verbose_name = "Plan Subscription"
        verbose_name_plural = "Plan Subscriptions"

    def __str__(self):
        return f"{self.tenant.name} — {self.plan} ({self.billing_status})"
