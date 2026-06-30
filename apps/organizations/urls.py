"""
URL configuration for the organizations app.

All routes are under /api/v1/organizations/ (see config/urls.py).
"""

from django.urls import path

from apps.organizations.views.branch import BranchActionsView, BranchListCreateView, BranchSettingsView
from apps.organizations.views.institution import (
    AttendanceSettingsView,
    InstitutionSettingsView,
    SubdomainCheckView,
)
from apps.organizations.views.plan import PlanView
from apps.organizations.views.platform_student_subscription import (
    PlatformStudentSubscriptionActionsView,
    PlatformStudentSubscriptionListView,
)
from apps.organizations.views.platform_ops import (
    PlatformAuditView,
    PlatformIntegrationHealthView,
    PlatformMaintenanceView,
    PlatformPlanFeaturesView,
    PlatformSettingsView,
    PlatformSupportView,
    PlatformTicketActionsView,
    PlatformTicketsView,
    PlatformTrialActionsView,
    PlatformTrialsView,
)
from apps.organizations.views.platform_plan import (
    PlatformPlanLimitsValidateView,
    PlatformPlanView,
)
from apps.organizations.views.platform_tenant import (
    PlatformTenantActionsView,
    PlatformTenantDetailView,
    PlatformTenantListCreateView,
)
from apps.organizations.views.tenant import TenantConfigView

app_name = "organizations"

urlpatterns = [
    # Public — login page bootstrap
    path("tenant-config/", TenantConfigView.as_view(), name="tenant-config"),

    # Super-admin — branches
    path("branches/", BranchListCreateView.as_view(), name="branches"),
    path("branches/actions/", BranchActionsView.as_view(), name="branch-actions"),
    path("branches/<uuid:branch_id>/settings/", BranchSettingsView.as_view(), name="branch-settings"),

    # Super-admin — institution settings
    path("institution-settings/", InstitutionSettingsView.as_view(), name="institution-settings"),
    path("attendance-settings/", AttendanceSettingsView.as_view(), name="attendance-settings"),

    # Super-admin — plan
    path("plan/", PlanView.as_view(), name="plan"),

    # Onboarding helper
    path("subdomain-check/", SubdomainCheckView.as_view(), name="subdomain-check"),

    # Platform-owner — tenant management
    path("platform/tenants/", PlatformTenantListCreateView.as_view(), name="platform-tenants"),
    path("platform/tenants/actions/", PlatformTenantActionsView.as_view(), name="platform-tenant-actions"),
    path("platform/tenants/<uuid:tenant_id>/", PlatformTenantDetailView.as_view(), name="platform-tenant-detail"),
    path(
        "platform/student-subscriptions/",
        PlatformStudentSubscriptionListView.as_view(),
        name="platform-student-subscriptions",
    ),
    path(
        "platform/student-subscriptions/actions/",
        PlatformStudentSubscriptionActionsView.as_view(),
        name="platform-student-subscription-actions",
    ),

    # Platform-owner — plan management
    path("platform/plans/", PlatformPlanView.as_view(), name="platform-plans"),
    path(
        "platform/plan-limits/validate/",
        PlatformPlanLimitsValidateView.as_view(),
        name="platform-plan-limits-validate",
    ),

    # Platform-owner — operational
    path("platform/audit/", PlatformAuditView.as_view(), name="platform-audit"),
    path("platform/trials/", PlatformTrialsView.as_view(), name="platform-trials"),
    path("platform/trials/actions/", PlatformTrialActionsView.as_view(), name="platform-trial-actions"),
    path("platform/tickets/", PlatformTicketsView.as_view(), name="platform-tickets"),
    path("platform/tickets/actions/", PlatformTicketActionsView.as_view(), name="platform-ticket-actions"),
    path("platform/support/", PlatformSupportView.as_view(), name="platform-support"),
    path("platform/settings/", PlatformSettingsView.as_view(), name="platform-settings"),
    path("platform/plan-features/", PlatformPlanFeaturesView.as_view(), name="platform-plan-features"),
    path("platform/maintenance/", PlatformMaintenanceView.as_view(), name="platform-maintenance"),
    path(
        "platform/integrations/health/",
        PlatformIntegrationHealthView.as_view(),
        name="platform-integration-health",
    ),
]
