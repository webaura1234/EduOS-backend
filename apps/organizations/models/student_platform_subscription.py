"""Per-student platform SaaS subscription (annual fee per enrolled student)."""

from django.db import models

from apps.core.models import BaseModel
from apps.organizations.enums import PlanType, StudentPlatformSubscriptionStatus


class StudentPlatformSubscription(BaseModel):
    """One row per active student per academic year on the platform."""

    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="student_platform_subscriptions",
    )
    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="student_platform_subscriptions",
    )
    student_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="platform_subscriptions",
    )
    academic_year = models.CharField(max_length=9, db_index=True)
    plan = models.CharField(max_length=20, choices=PlanType.choices, default=PlanType.STARTER)
    annual_fee_inr = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=StudentPlatformSubscriptionStatus.choices,
        default=StudentPlatformSubscriptionStatus.UNPAID,
        db_index=True,
    )
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "organizations_student_platform_subscription"
        constraints = [
            models.UniqueConstraint(
                fields=["student_user", "academic_year"],
                name="unique_student_platform_sub_per_year",
            ),
        ]
        indexes = [
            models.Index(fields=["tenant", "status"]),
            models.Index(fields=["branch", "status"]),
            models.Index(fields=["tenant", "branch"]),
        ]

    def __str__(self):
        return f"{self.student_user_id} {self.academic_year} ({self.status})"
