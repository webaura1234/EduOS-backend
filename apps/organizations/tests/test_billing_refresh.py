"""Tests for materialized tenant billing refresh (licenses + payments)."""

import datetime

import pytest
from django.utils import timezone

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.organizations.billing.billing_refresh import (
    billing_dict_for_tenant,
    refresh_tenant_billing,
    subscription_collected_trend,
)
from apps.organizations.billing.license_allocator import on_student_enrolled, record_payment
from apps.organizations.models import (
    PlatformPlanDefinition,
    TenantLicensePricing,
    TenantLicenseSummary,
)
from apps.organizations.tests.factories import (
    BranchFactory,
    PlanSubscriptionFactory,
    TenantFactory,
)

pytestmark = pytest.mark.django_db


def _seed_catalog():
    PlatformPlanDefinition.objects.update_or_create(
        plan="standard",
        defaults={"label": "Standard ERP", "price_per_student_inr": 299},
    )


def test_refresh_tenant_billing_persists_net_and_annual_from_licenses():
    _seed_catalog()
    tenant = TenantFactory()
    branch = BranchFactory(tenant=tenant)
    PlanSubscriptionFactory(tenant=tenant, plan="standard")
    TenantLicensePricing.objects.create(tenant=tenant, discount_percent=10)

    record_payment(
        tenant,
        licenses_granted=3,
        amount_inr=807,
        payment_mode="cash",
        paid_at=timezone.localdate(),
    )
    for _ in range(3):
        student = UserFactory(tenant=tenant, branch=branch, role=Role.STUDENT)
        on_student_enrolled(student)

    refresh_tenant_billing(tenant.pk)

    pricing = TenantLicensePricing.objects.get(tenant=tenant)
    assert pricing.net_unit_price_inr == 269

    summary = TenantLicenseSummary.objects.get(tenant=tenant)
    assert summary.licenses_consumed == 3
    assert summary.active_student_count == 3
    assert summary.annual_subscription_inr == 807
    assert summary.collected_subscription_inr == 807


def test_discount_patch_updates_materialized_totals():
    from django.urls import reverse
    from rest_framework.test import APIClient

    from apps.accounts.tokens import generate_access_token

    _seed_catalog()
    tenant = TenantFactory()
    branch = BranchFactory(tenant=tenant)
    PlanSubscriptionFactory(tenant=tenant, plan="standard")
    owner = UserFactory(
        role=Role.PLATFORM_OWNER,
        tenant=None,
        branch=None,
        phone="+919700000199",
        custom_login_id=None,
        must_change_password=False,
    )
    record_payment(
        tenant,
        licenses_granted=1,
        amount_inr=299,
        payment_mode="cash",
        paid_at=timezone.localdate(),
    )
    student = UserFactory(tenant=tenant, branch=branch, role=Role.STUDENT)
    on_student_enrolled(student)

    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(owner)}")
    resp = api.patch(
        reverse("organizations:platform-licensing-tenant-pricing", kwargs={"tenant_id": tenant.pk}),
        {"discountPercent": 20},
        format="json",
    )
    assert resp.status_code == 200

    pricing = TenantLicensePricing.objects.get(tenant=tenant)
    assert pricing.net_unit_price_inr == 239

    summary = TenantLicenseSummary.objects.get(tenant=tenant)
    assert summary.annual_subscription_inr == 239
    assert summary.active_student_count == 1


def test_billing_dict_branch_licensed_counts():
    _seed_catalog()
    tenant = TenantFactory()
    b1 = BranchFactory(tenant=tenant, name="Main")
    b2 = BranchFactory(tenant=tenant, name="North")
    PlanSubscriptionFactory(tenant=tenant, plan="standard")
    TenantLicensePricing.objects.create(tenant=tenant, discount_percent=0)

    record_payment(
        tenant,
        licenses_granted=2,
        amount_inr=598,
        payment_mode="cash",
        paid_at=timezone.localdate(),
    )
    on_student_enrolled(UserFactory(tenant=tenant, branch=b1, role=Role.STUDENT))
    on_student_enrolled(UserFactory(tenant=tenant, branch=b2, role=Role.STUDENT))
    refresh_tenant_billing(tenant.pk)

    billing = billing_dict_for_tenant(tenant.pk)
    assert len(billing["branches"]) == 2
    unit_prices = {row["unitPricePerStudentInr"] for row in billing["branches"]}
    assert unit_prices == {299}
    assert sum(row["licensedCount"] for row in billing["branches"]) == 2
    assert billing["licensesConsumed"] == 2
    assert billing["collectedSubscriptionInr"] == 598


def test_subscription_collected_trend_groups_license_payments():
    _seed_catalog()
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, plan="standard")

    record_payment(
        tenant,
        licenses_granted=2,
        amount_inr=500,
        payment_mode="cash",
        paid_at=datetime.date(2026, 6, 15),
    )

    trend = subscription_collected_trend(months=6)
    june = next((p for p in trend if p["month"] == "Jun 2026"), None)
    assert june is not None
    assert june["collectedInr"] == 500
    assert sum(p["collectedInr"] for p in trend) == 500
