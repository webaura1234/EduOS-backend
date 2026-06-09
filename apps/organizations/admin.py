"""Django admin registrations for the organizations app."""

from django.contrib import admin

from apps.organizations.models import (
    Branch,
    FeatureFlag,
    PlanSubscription,
    Tenant,
    TenantQuota,
    TenantSettings,
)


@admin.register(Tenant)
class TenantAdmin(admin.ModelAdmin):
    list_display = ("name", "subdomain", "institution_type", "status", "parent_access_enabled")
    list_filter = ("institution_type", "status")
    search_fields = ("name", "subdomain", "city")


@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ("name", "tenant", "code", "is_primary")
    list_filter = ("is_primary",)
    search_fields = ("name", "code")
    raw_id_fields = ("tenant",)


@admin.register(TenantSettings)
class TenantSettingsAdmin(admin.ModelAdmin):
    list_display = ("tenant", "attendance_threshold_percent", "sms_enabled", "email_enabled")
    raw_id_fields = ("tenant",)


@admin.register(PlanSubscription)
class PlanSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("tenant", "plan", "billing_status", "valid_until")
    list_filter = ("plan", "billing_status")
    raw_id_fields = ("tenant",)


@admin.register(TenantQuota)
class TenantQuotaAdmin(admin.ModelAdmin):
    list_display = ("tenant", "resource", "period", "period_start", "usage", "soft_cap", "hard_cap")
    list_filter = ("resource", "period")
    raw_id_fields = ("tenant",)


@admin.register(FeatureFlag)
class FeatureFlagAdmin(admin.ModelAdmin):
    list_display = ("key", "tenant", "enabled", "rollout_percent")
    list_filter = ("enabled",)
    search_fields = ("key",)
    raw_id_fields = ("tenant",)
