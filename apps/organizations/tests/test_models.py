"""Model tests for the organizations app — TenantQuota and FeatureFlag."""

import datetime

import pytest
from django.db import IntegrityError

from apps.organizations.models import FeatureFlag, QuotaResource
from apps.organizations.tests.factories import (
    FeatureFlagFactory,
    TenantFactory,
    TenantQuotaFactory,
)

pytestmark = pytest.mark.django_db


# ── TenantQuota ───────────────────────────────────────────────────────────────
def test_quota_cap_helpers():
    q = TenantQuotaFactory(usage=150, soft_cap=180, hard_cap=200)
    assert q.is_over_soft_cap is False
    assert q.is_over_hard_cap is False
    assert q.remaining == 50
    assert q.would_exceed_hard_cap(60) is True
    assert q.would_exceed_hard_cap(40) is False


def test_quota_over_caps_and_uncapped():
    over = TenantQuotaFactory(usage=200, soft_cap=180, hard_cap=200)
    assert over.is_over_soft_cap is True
    assert over.is_over_hard_cap is True

    uncapped = TenantQuotaFactory(usage=10_000, soft_cap=0, hard_cap=0)
    assert uncapped.is_over_soft_cap is False
    assert uncapped.is_over_hard_cap is False
    assert uncapped.remaining is None


def test_quota_unique_per_tenant_resource_period():
    tenant = TenantFactory()
    start = datetime.date.today().replace(day=1)
    TenantQuotaFactory(tenant=tenant, resource=QuotaResource.SMS_COUNT, period_start=start)
    with pytest.raises(IntegrityError):
        TenantQuotaFactory(tenant=tenant, resource=QuotaResource.SMS_COUNT, period_start=start)


# ── FeatureFlag ───────────────────────────────────────────────────────────────
def test_feature_flag_same_key_allowed_across_tenants():
    FeatureFlagFactory(key="ai_paper", tenant=TenantFactory())
    second = FeatureFlagFactory(key="ai_paper", tenant=TenantFactory())
    assert second.pk is not None


def test_feature_flag_key_unique_within_tenant():
    tenant = TenantFactory()
    FeatureFlagFactory(key="ai_paper", tenant=tenant)
    with pytest.raises(IntegrityError):
        FeatureFlagFactory(key="ai_paper", tenant=tenant)


def test_global_feature_flag_key_unique():
    FeatureFlag.objects.create(key="global_maintenance", tenant=None, enabled=True)
    with pytest.raises(IntegrityError):
        FeatureFlag.objects.create(key="global_maintenance", tenant=None, enabled=False)
