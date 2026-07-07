"""Tests for unified pricing service."""

import pytest

from apps.organizations.billing import pricing
from apps.organizations.models import PlatformPlanDefinition, TenantLicensePricing
from apps.organizations.tests.factories import PlanSubscriptionFactory, TenantFactory

pytestmark = pytest.mark.django_db


def test_list_price_from_db_catalog():
    PlatformPlanDefinition.objects.update_or_create(
        plan="standard",
        defaults={"label": "Standard ERP", "price_per_student_inr": 350},
    )
    assert pricing.list_price_for_plan("standard") == 350


def test_net_price_applies_tenant_discount():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, plan="standard")
    PlatformPlanDefinition.objects.update_or_create(
        plan="standard",
        defaults={"label": "Standard ERP", "price_per_student_inr": 299},
    )
    TenantLicensePricing.objects.create(tenant=tenant, discount_percent=20)
    assert pricing.net_unit_price_inr(tenant.pk, "standard") == 239


def test_pricing_for_tenant_shape():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, plan="ai")
    PlatformPlanDefinition.objects.update_or_create(
        plan="ai",
        defaults={"label": "AI ERP", "price_per_student_inr": 499},
    )
    row = pricing.pricing_for_tenant(tenant.pk)
    assert row["plan"] == "ai"
    assert row["listPricePerStudentInr"] == 499
    assert row["discountPercent"] == 0
    assert row["unitPricePerStudentInr"] == 499
