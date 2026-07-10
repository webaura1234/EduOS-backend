"""Reusable fee head catalog (branch-scoped)."""

from django.db import models

from apps.core.models import BaseModel
from apps.fees.enums import (
    FeeComponentKind,
    FeeHeadBillingType,
    FeeHeadChargeType,
    FeeHeadRefundType,
)


class FeeHead(BaseModel):
    """Branch-scoped master list of fee heads reused across academic years."""

    branch = models.ForeignKey("organizations.Branch", on_delete=models.CASCADE, related_name="fee_heads")
    name = models.CharField(max_length=120)
    kind = models.CharField(max_length=15, choices=FeeComponentKind.choices, default=FeeComponentKind.OTHER)
    charge_type = models.CharField(max_length=12, choices=FeeHeadChargeType.choices, default=FeeHeadChargeType.MANDATORY)
    billing_type = models.CharField(max_length=12, choices=FeeHeadBillingType.choices, default=FeeHeadBillingType.RECURRING)
    refund_type = models.CharField(max_length=16, choices=FeeHeadRefundType.choices, default=FeeHeadRefundType.NON_REFUNDABLE)

    class Meta:
        db_table = "fees_fee_head"
        verbose_name = "Fee Head"
        verbose_name_plural = "Fee Heads"
        constraints = [
            models.UniqueConstraint(fields=["branch", "name"], name="unique_fee_head_name_per_branch"),
        ]

    def __str__(self):
        return self.name
