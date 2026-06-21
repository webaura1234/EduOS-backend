"""Resolve white-label branding (logo + colors) into the camelCase theme object
both the web app and the per-tenant mobile apps consume.

Single source of truth: the tenant defines the baseline brand; a branch may override
any field (blank = inherit). Clients apply this theme over their built-in fallback.
"""

from apps.organizations.models.institution import (
    DEFAULT_ACCENT_COLOR,
    DEFAULT_PRIMARY_COLOR,
)


def _logo_url(key: str) -> str | None:
    """Map a stored logo key/URL to something a client can load. Centralized so the
    eventual S3-key → signed-URL conversion only has to change in one place."""
    return key or None


def tenant_theme(tenant) -> dict:
    """Baseline brand for a tenant (used at login, before a branch is known)."""
    return {
        "logoUrl": _logo_url(tenant.logo_s3_key),
        "primaryColor": tenant.primary_color or DEFAULT_PRIMARY_COLOR,
        "accentColor": tenant.accent_color or DEFAULT_ACCENT_COLOR,
    }


def branch_theme(branch) -> dict:
    """Effective brand for a branch — its overrides, falling back to the tenant."""
    return {
        "logoUrl": _logo_url(branch.effective_logo_key),
        "primaryColor": branch.effective_primary_color or DEFAULT_PRIMARY_COLOR,
        "accentColor": branch.effective_accent_color or DEFAULT_ACCENT_COLOR,
    }
