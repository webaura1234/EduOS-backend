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
    StudentPlatformSubscriptionStatus,
)

from .branch import Branch
from .feature_flag import FeatureFlag
from .institution import Tenant
from .plan import PlanSubscription, TenantQuota
from .platform_ops import (
    PlatformAuditLog,
    PlatformGlobalAnnouncement,
    PlatformMaintenanceSetting,
    PlatformPlanDefinition,
    PlatformSupportModeLog,
    PlatformSupportSession,
    PlatformSupportTicket,
    PlatformSupportTicketComment,
)
from .settings import TenantSettings
from .student_platform_subscription import StudentPlatformSubscription

__all__ = [
    # Models
    "Tenant",
    "Branch",
    "TenantSettings",
    "PlanSubscription",
    "TenantQuota",
    "FeatureFlag",
    "StudentPlatformSubscription",
    "PlatformAuditLog",
    "PlatformSupportSession",
    "PlatformSupportModeLog",
    "PlatformGlobalAnnouncement",
    "PlatformMaintenanceSetting",
    "PlatformPlanDefinition",
    "PlatformSupportTicket",
    "PlatformSupportTicketComment",
    # Enums
    "InstitutionType",
    "InstitutionStatus",
    "PlanType",
    "BillingStatus",
    "StudentPlatformSubscriptionStatus",
    "QuotaResource",
    "QuotaPeriod",
]
