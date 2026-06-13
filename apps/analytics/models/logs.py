"""
Analytics — operational logs.

  - AuditLog       → append-only, hash-chained record of sensitive actions (F-239)
  - SupportModeLog → platform-owner support-session tracking (F-240)
"""

from django.db import models

from apps.core.models import BaseModel


class AuditLog(BaseModel):
    """Append-only, per-tenant hash-chained audit record (F-239 / EC-PRIV-06).

    Each row links to the previous one in the tenant's chain via `prev_hash`; `row_hash`
    is the SHA-256 of the canonical fields + prev_hash. Tampering breaks the chain, which
    `analytics.interactors.audit.verify_chain` detects. No update/delete helpers exist —
    immutability is enforced in the queries layer (DB trigger is an Ops seam).
    """

    tenant = models.ForeignKey(
        "organizations.Tenant", on_delete=models.CASCADE, related_name="audit_logs"
    )
    actor_user = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="audit_actions",
    )
    action = models.CharField(max_length=100, db_index=True)  # e.g. "result.publish"
    entity_type = models.CharField(max_length=100, blank=True, default="")
    entity_id = models.CharField(max_length=64, blank=True, default="")
    diff = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")
    correlation_id = models.CharField(max_length=64, blank=True, default="")

    prev_hash = models.CharField(max_length=64, blank=True, default="")
    row_hash = models.CharField(max_length=64, db_index=True)

    class Meta:
        db_table = "analytics_audit_log"
        indexes = [
            models.Index(fields=["tenant", "created_at"]),
            models.Index(fields=["tenant", "action"]),
        ]

    def __str__(self):
        return f"AuditLog({self.action} by {self.actor_user_id})"


class SupportModeLog(BaseModel):
    """Platform-owner support-session start/end + actions (F-240)."""

    platform_owner = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="support_sessions",
    )
    tenant = models.ForeignKey(
        "organizations.Tenant", on_delete=models.CASCADE, related_name="support_sessions"
    )
    started_at = models.DateTimeField()
    ended_at = models.DateTimeField(null=True, blank=True)
    reason = models.TextField(blank=True, default="")
    ticket_ref = models.CharField(max_length=100, blank=True, default="")
    read_only = models.BooleanField(default=True)
    actions = models.JSONField(default=list, blank=True)

    class Meta:
        db_table = "analytics_support_mode_log"
        indexes = [models.Index(fields=["tenant", "started_at"])]

    def __str__(self):
        return f"SupportModeLog({self.tenant_id})"
