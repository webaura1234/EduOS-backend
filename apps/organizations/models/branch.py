"""
Branch — a physical campus / location within a Tenant.

Every operational record (user, student, attendance, fee) is scoped to a Branch.
Super Admins see all branches; Admins are typically scoped to one.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel


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
