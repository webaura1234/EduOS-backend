"""
Organizations models — the multi-tenant root domain.

Hierarchy:
    Tenant (Institution)
      ├── Branch (≥1)
      ├── TenantSettings (1:1)
      ├── PlanSubscription (1:1)
      ├── TenantQuota (per resource/period)
      └── FeatureFlag (per-tenant or global)

Enums live in ``apps.organizations.enums``.
"""

from apps.organizations.enums import (
    BillingStatus,
    InstitutionStatus,
    InstitutionType,
    PlanType,
    QuotaPeriod,
    QuotaResource,
)

from .branch import Branch
from .feature_flag import FeatureFlag
from .institution import Tenant
from .plan import PlanSubscription, TenantQuota
from .settings import TenantSettings

__all__ = [
    # Models
    "Tenant",
    "Branch",
    "TenantSettings",
    "PlanSubscription",
    "TenantQuota",
    "FeatureFlag",
    # Enums
    "InstitutionType",
    "InstitutionStatus",
    "PlanType",
    "BillingStatus",
    "QuotaResource",
    "QuotaPeriod",
]
