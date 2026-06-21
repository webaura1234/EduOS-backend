"""
Branch — a physical campus / location within a Tenant.

Every operational record (user, student, attendance, fee) is scoped to a Branch.
Super Admins see all branches; Admins are typically scoped to one.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel
from apps.organizations.models.institution import hex_color_validator


def default_working_days() -> list:
    """Working day-of-week numbers (0=Sun..6=Sat). Default: Mon–Sat working."""
    return [1, 2, 3, 4, 5, 6]


class Branch(BaseModel):
    """
    A campus within a Tenant.

    Every Tenant has at least one Branch (created at onboarding, usually
    "Main Campus"). `is_primary` marks that default campus.
    """

    tenant = models.ForeignKey(
        "organizations.Tenant",
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

    # Branding overrides — blank means "inherit from the tenant" (effective_* props below).
    # Use these only when a branch is a distinct sub-brand (e.g. a College under a School group).
    logo_s3_key = models.CharField(max_length=500, blank=True, default="")
    primary_color = models.CharField(
        max_length=7, blank=True, default="", validators=[hex_color_validator],
    )
    accent_color = models.CharField(
        max_length=7, blank=True, default="", validators=[hex_color_validator],
    )

    # Address (may differ from Tenant address for multi-campus)
    address = models.TextField(blank=True, default="")
    city = models.CharField(max_length=100, blank=True, default="")
    state = models.CharField(max_length=100, blank=True, default="")
    postal_code = models.CharField(max_length=20, blank=True, default="")
    phone = models.CharField(max_length=20, blank=True, default="")

    # Localization — inherits from Tenant if null
    timezone = models.CharField(max_length=50, blank=True, null=True)

    # Working days for the academic calendar (list of day-of-week ints, 0=Sun..6=Sat).
    working_days = models.JSONField(default=default_working_days, blank=True)

    # Academic calendar config
    academic_year_start_month = models.PositiveSmallIntegerField(
        default=4,
        validators=[MinValueValidator(1), MaxValueValidator(12)],
        help_text="Month (1-12) when the academic year starts. Default: April.",
    )

    # Geo-fence for attendance (F-103). When lat/lng + radius are set, the backend
    # validates a marking faculty's location against this point.
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    geofence_radius_m = models.PositiveIntegerField(
        null=True, blank=True, help_text="Allowed radius in metres; null = geo-fence disabled.",
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
    def effective_timezone(self) -> str:
        return self.timezone or self.tenant.timezone

    # Branding inheritance — a branch value wins only when set; otherwise inherit tenant.
    @property
    def effective_logo_key(self) -> str:
        return self.logo_s3_key or self.tenant.logo_s3_key

    @property
    def effective_primary_color(self) -> str:
        return self.primary_color or self.tenant.primary_color

    @property
    def effective_accent_color(self) -> str:
        return self.accent_color or self.tenant.accent_color
