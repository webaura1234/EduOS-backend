"""White-label theming — tenant defaults, branch override/inheritance, API exposure."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.organizations.branding import branch_theme, tenant_theme
from apps.organizations.models.institution import (
    DEFAULT_ACCENT_COLOR,
    DEFAULT_PRIMARY_COLOR,
)
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def test_tenant_theme_uses_defaults_when_unset():
    tenant = TenantFactory()
    theme = tenant_theme(tenant)
    assert theme["primaryColor"] == DEFAULT_PRIMARY_COLOR
    assert theme["accentColor"] == DEFAULT_ACCENT_COLOR
    assert theme["logoUrl"] is None


def test_branch_inherits_tenant_brand_when_no_override():
    tenant = TenantFactory(primary_color="#111111", accent_color="#222222",
                           logo_s3_key="tenant/logo.png")
    branch = BranchFactory(tenant=tenant)
    theme = branch_theme(branch)
    assert theme["primaryColor"] == "#111111"
    assert theme["accentColor"] == "#222222"
    assert theme["logoUrl"] == "tenant/logo.png"


def test_branch_override_wins_over_tenant():
    tenant = TenantFactory(primary_color="#111111", accent_color="#222222",
                           logo_s3_key="tenant/logo.png")
    branch = BranchFactory(tenant=tenant, primary_color="#ABCDEF",
                           logo_s3_key="branch/college-logo.png")
    theme = branch_theme(branch)
    assert theme["primaryColor"] == "#ABCDEF"        # branch override
    assert theme["logoUrl"] == "branch/college-logo.png"
    assert theme["accentColor"] == "#222222"          # inherited from tenant


def test_blank_everywhere_falls_back_to_defaults():
    # Tenant + branch both blank → green brand defaults (the original palette).
    branch = BranchFactory(tenant=TenantFactory())
    theme = branch_theme(branch)
    assert theme["primaryColor"] == DEFAULT_PRIMARY_COLOR
    assert theme["accentColor"] == DEFAULT_ACCENT_COLOR


def test_tenant_config_endpoint_includes_theme():
    tenant = TenantFactory(subdomain="brandtest", primary_color="#123456")
    resp = APIClient().get(
        reverse("organizations:tenant-config"), {"subdomain": "brandtest"},
    )
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert body["theme"]["primaryColor"] == "#123456"
    assert body["logo_url"] == body["theme"]["logoUrl"]  # back-compat alias
