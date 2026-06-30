"""
Billing & quota models.

  - PlanSubscription → one per tenant; the plan tier and its static limits.
  - TenantQuota      → per-resource live usage counters with soft/hard caps,
                       checked on every metered write.
"""

from django.db import models

from apps.core.models import BaseModel
from apps.organizations.enums import (
    BillingStatus,
    PlanType,
    QuotaPeriod,
    QuotaResource,
)


class PlanSubscription(BaseModel):
    """The billing plan for a Tenant (one subscription per tenant)."""

    tenant = models.OneToOneField(
        "organizations.Tenant",
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

    # Static limits for the plan tier (live usage is tracked in TenantQuota).
    student_limit = models.PositiveIntegerField(default=200)
    storage_limit_gb = models.PositiveIntegerField(default=10)
    sms_quota_per_month = models.PositiveIntegerField(default=500)
    ai_token_quota_per_month = models.PositiveIntegerField(default=10000)
    api_rpm_limit = models.PositiveIntegerField(default=100)

    valid_until = models.DateField(null=True, blank=True)

    # Trial lifecycle dates (populated for billing_status=TRIAL).
    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)
    grace_ends_at = models.DateTimeField(null=True, blank=True)
    grace_started_at = models.DateTimeField(null=True, blank=True)

    # Billing snapshot — updated on payment events.
    last_paid_at = models.DateTimeField(null=True, blank=True)
    next_due_at = models.DateTimeField(null=True, blank=True)
    amount_due_inr = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        db_table = "organizations_plan_subscription"
        verbose_name = "Plan Subscription"
        verbose_name_plural = "Plan Subscriptions"

    def __str__(self):
        return f"{self.tenant.name} — {self.plan} ({self.billing_status})"


class TenantQuota(BaseModel):
    """
    A metered usage counter for one resource over one accounting window.

    Soft cap → warn / nudge to upgrade. Hard cap → block the write.
    `period=total` rows use a fixed sentinel period_start; `period=month` rows
    use the first day of the calendar month.
    """

    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="quotas",
    )
    resource = models.CharField(max_length=20, choices=QuotaResource.choices, db_index=True)
    period = models.CharField(max_length=10, choices=QuotaPeriod.choices, default=QuotaPeriod.MONTH)
    period_start = models.DateField(help_text="First day of the window (or a sentinel for 'total').")

    usage = models.BigIntegerField(default=0)
    soft_cap = models.BigIntegerField(default=0, help_text="0 = no soft cap.")
    hard_cap = models.BigIntegerField(default=0, help_text="0 = no hard cap.")

    class Meta:
        db_table = "organizations_tenant_quota"
        verbose_name = "Tenant Quota"
        verbose_name_plural = "Tenant Quotas"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "resource", "period_start"],
                name="unique_quota_per_tenant_resource_period",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "resource", "period_start"]),
        ]

    def __str__(self):
        return f"{self.tenant.name} — {self.resource} {self.usage}/{self.hard_cap or '∞'}"

    @property
    def is_over_soft_cap(self) -> bool:
        return self.soft_cap > 0 and self.usage >= self.soft_cap

    @property
    def is_over_hard_cap(self) -> bool:
        return self.hard_cap > 0 and self.usage >= self.hard_cap

    @property
    def remaining(self) -> int | None:
        """Units left before the hard cap, or None when uncapped."""
        if self.hard_cap <= 0:
            return None
        return max(self.hard_cap - self.usage, 0)

    def would_exceed_hard_cap(self, amount: int) -> bool:
        """Whether adding `amount` would cross the hard cap (used before a metered write)."""
        return self.hard_cap > 0 and (self.usage + amount) > self.hard_cap
