"""
Institution (Tenant) — the root of all multi-tenant data isolation.

Each school or college that subscribes to EduOS gets exactly one Tenant row.
Every other record in the platform is scoped under a Tenant (and usually a Branch).
"""

from django.core.validators import RegexValidator
from django.db import models

from apps.core.models import BaseModel
from apps.organizations.enums import InstitutionStatus, InstitutionType

subdomain_validator = RegexValidator(
    regex=r"^[a-z0-9][a-z0-9-]{1,61}[a-z0-9]$",
    message="Subdomain must be lowercase alphanumeric with hyphens (e.g. greenfield-academy).",
)

# Branding colors are stored as #RRGGBB hex (validated so a bad value can't break clients).
hex_color_validator = RegexValidator(
    regex=r"^#(?:[0-9a-fA-F]{6})$",
    message="Color must be a #RRGGBB hex value (e.g. #2563EB).",
)

# Brand defaults — every client falls back to these when nothing is configured.
# Matches the original design palette (tokens.css --eduos-primary / --eduos-brand).
DEFAULT_PRIMARY_COLOR = "#1a5f4a"
DEFAULT_ACCENT_COLOR = "#004634"


class Tenant(BaseModel):
    """
    Institution — the root tenant entity.

    Subdomain is globally unique and forms the white-labeled login URL,
    e.g. ``greenfield.eduos.app``.
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
        help_text="Immutable after the first academic-year rollover.",
    )

    # Branding — the baseline brand every client (web + mobile) falls back to.
    logo_s3_key = models.CharField(max_length=500, blank=True, default="")
    # Blank = use the code default (DEFAULT_*). Set only to override the brand color.
    primary_color = models.CharField(
        max_length=7, blank=True, default="", validators=[hex_color_validator],
    )
    accent_color = models.CharField(
        max_length=7, blank=True, default="", validators=[hex_color_validator],
    )

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

    # Flexible feature toggles / branding kept inline for cheap reads.
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "organizations_tenant"
        verbose_name = "Tenant"
        verbose_name_plural = "Tenants"
        # status and city already carry field-level db_index (see fields above).

    def __str__(self):
        return f"{self.name} ({self.subdomain})"

    @property
    def is_school(self) -> bool:
        return self.institution_type == InstitutionType.SCHOOL

    @property
    def is_college(self) -> bool:
        return self.institution_type == InstitutionType.COLLEGE

    @property
    def has_active_status(self) -> bool:
        """True when the institution lifecycle status is active (NOT BaseModel.is_active)."""
        return self.status == InstitutionStatus.ACTIVE
