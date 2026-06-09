"""
URL configuration for the organizations app.

All routes are under /api/v1/organizations/ (see config/urls.py).
"""

from django.urls import path

from apps.organizations.views.branch import BranchActionsView, BranchListCreateView
from apps.organizations.views.institution import (
    InstitutionSettingsView,
    SubdomainCheckView,
)
from apps.organizations.views.plan import PlanView
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

    # Super-admin — institution settings
    path("institution-settings/", InstitutionSettingsView.as_view(), name="institution-settings"),

    # Super-admin — plan
    path("plan/", PlanView.as_view(), name="plan"),

    # Onboarding helper
    path("subdomain-check/", SubdomainCheckView.as_view(), name="subdomain-check"),

    # Platform-owner — tenant management
    path("platform/tenants/", PlatformTenantListCreateView.as_view(), name="platform-tenants"),
    path("platform/tenants/actions/", PlatformTenantActionsView.as_view(), name="platform-tenant-actions"),
    path("platform/tenants/<uuid:tenant_id>/", PlatformTenantDetailView.as_view(), name="platform-tenant-detail"),
]
