"""
Platform-owner operational models.

These back the platform-owner admin screens:
  - PlatformAuditLog             → append-only action log
  - PlatformSupportSession       → active (or ended) support impersonation
  - PlatformSupportModeLog       → per-action log while inside support mode
  - PlatformGlobalAnnouncement   → broadcast banners shown to all tenants
  - PlatformMaintenanceSetting   → singleton maintenance-mode toggle
  - PlatformPlanDefinition       → editable plan metadata (label, limits, features)
  - PlatformSupportTicket        → IT support tickets raised by tenant super-admins
  - PlatformSupportTicketComment → comments/notes on a ticket
"""

from django.db import models

from apps.core.models import BaseModel

AUDIT_CATEGORY_CHOICES = [
    ("support", "Support"),
    ("plan", "Plan"),
    ("tenant", "Tenant"),
    ("ticket", "Ticket"),
    ("announcement", "Announcement"),
    ("settings", "Settings"),
    ("billing", "Billing"),
]

ANNOUNCEMENT_SEVERITY_CHOICES = [
    ("info", "Info"),
    ("warning", "Warning"),
    ("critical", "Critical"),
]

TICKET_SEVERITY_CHOICES = [
    ("low", "Low"),
    ("medium", "Medium"),
    ("high", "High"),
    ("critical", "Critical"),
]

TICKET_STATUS_CHOICES = [
    ("open", "Open"),
    ("in_progress", "In Progress"),
    ("waiting_on_institution", "Waiting on Institution"),
    ("resolved", "Resolved"),
    ("closed", "Closed"),
]

TICKET_CATEGORY_CHOICES = [
    ("bug", "Bug"),
    ("data_issue", "Data Issue"),
    ("billing", "Billing"),
    ("access", "Access"),
    ("other", "Other"),
]

TICKET_COMMENT_ROLE_CHOICES = [
    ("super_admin", "Super Admin"),
    ("platform_owner", "Platform Owner"),
]


class PlatformAuditLog(BaseModel):
    """Immutable audit entry written on every platform-owner action."""

    category = models.CharField(max_length=20, choices=AUDIT_CATEGORY_CHOICES, db_index=True)
    action = models.CharField(max_length=100, db_index=True)
    detail = models.TextField(default="")
    actor_name = models.CharField(max_length=255, default="Platform Owner")
    actor = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    tenant_name = models.CharField(max_length=255, blank=True, default="")
    tenant_subdomain = models.CharField(max_length=100, blank=True, default="")

    class Meta:
        db_table = "platform_audit_log"
        ordering = ["-created_at"]
        verbose_name = "Platform Audit Log"
        verbose_name_plural = "Platform Audit Logs"

    def __str__(self):
        return f"{self.category}/{self.action} by {self.actor_name}"


class PlatformSupportSession(BaseModel):
    """
    Tracks a platform-owner's impersonation of a tenant.
    One row per session; exited_at=NULL means currently active.
    Only one active session should exist at a time (enforced by the service layer).
    """

    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="platform_support_sessions",
    )
    tenant_name = models.CharField(max_length=255, default="")
    tenant_subdomain = models.CharField(max_length=100, default="")
    started_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    started_by_name = models.CharField(max_length=255, default="Platform Owner")
    read_only = models.BooleanField(default=True)
    entered_at = models.DateTimeField()
    exited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "platform_support_session"
        ordering = ["-entered_at"]
        verbose_name = "Platform Support Session"
        verbose_name_plural = "Platform Support Sessions"

    def __str__(self):
        status = "active" if self.exited_at is None else "ended"
        return f"Support session [{status}] — {self.tenant_subdomain}"


class PlatformSupportModeLog(BaseModel):
    """One row per action performed during a support session."""

    session = models.ForeignKey(
        PlatformSupportSession,
        on_delete=models.CASCADE,
        related_name="logs",
    )
    tenant_subdomain = models.CharField(max_length=100)
    tenant_name = models.CharField(max_length=255)
    actor_name = models.CharField(max_length=255, default="Platform Owner")
    action = models.CharField(max_length=100)
    detail = models.TextField(default="")
    read_only = models.BooleanField(default=True)

    class Meta:
        db_table = "platform_support_mode_log"
        ordering = ["-created_at"]
        verbose_name = "Support Mode Log"
        verbose_name_plural = "Support Mode Logs"

    def __str__(self):
        return f"{self.action} @ {self.tenant_subdomain}"


class PlatformGlobalAnnouncement(BaseModel):
    """A global broadcast shown to all tenants' portals."""

    title = models.CharField(max_length=255)
    body = models.TextField()
    severity = models.CharField(
        max_length=10,
        choices=ANNOUNCEMENT_SEVERITY_CHOICES,
        default="info",
    )
    is_active = models.BooleanField(default=True, db_index=True)
    published_at = models.DateTimeField()
    published_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    published_by_name = models.CharField(max_length=255, default="Platform Owner")

    class Meta:
        db_table = "platform_global_announcement"
        ordering = ["-published_at"]
        verbose_name = "Global Announcement"
        verbose_name_plural = "Global Announcements"

    def __str__(self):
        return f"[{self.severity}] {self.title}"


class PlatformMaintenanceSetting(BaseModel):
    """
    Singleton table (always one row, id=1) for the maintenance-mode toggle.
    Created on first access by the query layer.
    """

    enabled = models.BooleanField(default=False)
    message = models.TextField(
        default=(
            "PiiAura is undergoing scheduled maintenance. "
            "Write operations are temporarily disabled."
        ),
    )
    block_writes = models.BooleanField(default=True)
    scheduled_end_at = models.DateTimeField(null=True, blank=True)
    updated_by_name = models.CharField(max_length=255, default="Platform Owner")

    class Meta:
        db_table = "platform_maintenance_setting"
        verbose_name = "Maintenance Setting"
        verbose_name_plural = "Maintenance Settings"

    def __str__(self):
        return f"Maintenance: {'ON' if self.enabled else 'OFF'}"


class PlatformPlanDefinition(BaseModel):
    """
    Editable metadata per plan tier. Seeded from PLAN_LIMITS on first access.
    Used for display (labels, features) and for limit validation.
    """

    plan = models.CharField(max_length=20, unique=True, db_index=True)
    label = models.CharField(max_length=50)
    max_branches = models.PositiveSmallIntegerField()
    max_students = models.PositiveIntegerField()
    included_features = models.JSONField(default=list)
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "platform_plan_definition"
        verbose_name = "Plan Definition"
        verbose_name_plural = "Plan Definitions"

    def __str__(self):
        return f"{self.label} ({self.plan})"


class PlatformSupportTicket(BaseModel):
    """IT support ticket raised by a tenant's super-admin with the platform owner."""

    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="platform_tickets",
    )
    title = models.CharField(max_length=255)
    severity = models.CharField(
        max_length=10,
        choices=TICKET_SEVERITY_CHOICES,
        default="medium",
        db_index=True,
    )
    status = models.CharField(
        max_length=30,
        choices=TICKET_STATUS_CHOICES,
        default="open",
        db_index=True,
    )
    category = models.CharField(max_length=20, choices=TICKET_CATEGORY_CHOICES, default="other")
    description = models.TextField(blank=True, default="")
    last_activity_at = models.DateTimeField(auto_now=True, db_index=True)

    class Meta:
        db_table = "platform_support_ticket"
        ordering = ["-last_activity_at"]
        verbose_name = "Support Ticket"
        verbose_name_plural = "Support Tickets"

    def __str__(self):
        return f"[{self.status}] {self.title} ({self.tenant.subdomain})"


class PlatformSupportTicketComment(BaseModel):
    """Comment or internal note on a support ticket."""

    ticket = models.ForeignKey(
        PlatformSupportTicket,
        on_delete=models.CASCADE,
        related_name="comments",
    )
    author = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    author_role = models.CharField(
        max_length=20,
        choices=TICKET_COMMENT_ROLE_CHOICES,
        default="super_admin",
    )
    author_name = models.CharField(max_length=255)
    message = models.TextField()

    class Meta:
        db_table = "platform_support_ticket_comment"
        ordering = ["created_at"]
        verbose_name = "Ticket Comment"
        verbose_name_plural = "Ticket Comments"

    def __str__(self):
        return f"Comment by {self.author_name} on {self.ticket_id}"
