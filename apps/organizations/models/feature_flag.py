"""
FeatureFlag — runtime feature gating, per-tenant or global.

A flag with tenant=null is global (applies to all tenants). A tenant-scoped row
overrides the global flag for that tenant. Supports gradual rollout by percentage
and an explicit user allowlist.
"""

from django.db import models

from apps.core.models import BaseModel


class FeatureFlag(BaseModel):
    """A single toggle, optionally scoped to a tenant, with rollout controls."""

    key = models.SlugField(
        max_length=100,
        db_index=True,
        help_text="Stable identifier, e.g. 'ai_question_paper'. Unique per tenant (and once globally).",
    )
    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="feature_flags",
        null=True,
        blank=True,
        help_text="Null = global flag applying to every tenant.",
    )
    enabled = models.BooleanField(default=False)
    rollout_percent = models.PositiveSmallIntegerField(
        default=100,
        help_text="0–100. Percentage of users the flag is on for when enabled.",
    )
    allowlist_user_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="Explicit user UUIDs always included, regardless of rollout_percent.",
    )
    description = models.TextField(blank=True, default="")

    class Meta:
        db_table = "organizations_feature_flag"
        verbose_name = "Feature Flag"
        verbose_name_plural = "Feature Flags"
        constraints = [
            # Unique per tenant, and unique among global rows (tenant IS NULL).
            models.UniqueConstraint(
                fields=["tenant", "key"],
                name="unique_feature_flag_key_per_tenant",
            ),
            models.UniqueConstraint(
                fields=["key"],
                condition=models.Q(tenant__isnull=True),
                name="unique_global_feature_flag_key",
            ),
        ]

    def __str__(self):
        scope = self.tenant.subdomain if self.tenant_id else "global"
        return f"{self.key} [{scope}] = {self.enabled}"
