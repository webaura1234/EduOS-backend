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
    LicenseEventType,
    LicenseInvoiceStatus,
    LicenseInvoiceType,
    LicensePaymentMode,
    PlanType,
    QuotaPeriod,
    QuotaResource,
    StudentLicenseStatus,
    SubscriptionPeriodStatus,
)

from .branch import Branch
from .feature_flag import FeatureFlag
from .institution import Tenant
from .licensing import (
    LicenseEvent,
    LicenseInvoice,
    LicensePayment,
    StudentLicense,
    TenantLicensePricing,
    TenantLicenseSummary,
    TenantSubscriptionPeriod,
)
from .plan import PlanSubscription, TenantQuota
from .ai_credits import StudentAiCreditBalance, StudentAiCreditTxn
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

__all__ = [
    # Models
    "Tenant",
    "Branch",
    "TenantSettings",
    "PlanSubscription",
    "TenantQuota",
    "StudentAiCreditBalance",
    "StudentAiCreditTxn",
    "FeatureFlag",
    "PlatformAuditLog",
    "PlatformSupportSession",
    "PlatformSupportModeLog",
    "PlatformGlobalAnnouncement",
    "PlatformMaintenanceSetting",
    "PlatformPlanDefinition",
    "PlatformSupportTicket",
    "PlatformSupportTicketComment",
    "TenantSubscriptionPeriod",
    "TenantLicensePricing",
    "LicenseInvoice",
    "LicensePayment",
    "StudentLicense",
    "LicenseEvent",
    "TenantLicenseSummary",
    # Enums
    "InstitutionType",
    "InstitutionStatus",
    "PlanType",
    "BillingStatus",
    "QuotaResource",
    "QuotaPeriod",
    "SubscriptionPeriodStatus",
    "LicenseInvoiceType",
    "LicenseInvoiceStatus",
    "LicensePaymentMode",
    "StudentLicenseStatus",
    "LicenseEventType",
]
