"""Tests for per-student AI credit metering."""

import pytest

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.organizations.billing.ai_access import AiAccessDenied
from apps.organizations.billing.ai_credits import (
    InsufficientAiCredits,
    consume_credits,
    grant_initial_credits,
    recharge_credits,
)
from apps.organizations.tests.factories import PlanSubscriptionFactory, TenantFactory

pytestmark = pytest.mark.django_db


def test_grant_and_consume_credits_on_ai_plan():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, plan="ai")
    student = UserFactory(role=Role.STUDENT, tenant=tenant)

    balance = grant_initial_credits(student_user=student)
    assert balance.balance == 50

    consume_credits(student_user=student, amount=10, idempotency_key="test-action-1")
    balance.refresh_from_db()
    assert balance.balance == 40

    # Idempotent consumption
    consume_credits(student_user=student, amount=10, idempotency_key="test-action-1")
    balance.refresh_from_db()
    assert balance.balance == 40


def test_standard_plan_blocks_ai_credits():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, plan="standard")
    student = UserFactory(role=Role.STUDENT, tenant=tenant)

    with pytest.raises(AiAccessDenied):
        grant_initial_credits(student_user=student)


def test_insufficient_credits_raises():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, plan="ai")
    student = UserFactory(role=Role.STUDENT, tenant=tenant)
    grant_initial_credits(student_user=student, amount=5)

    with pytest.raises(InsufficientAiCredits):
        consume_credits(student_user=student, amount=10, idempotency_key="big-action")


def test_recharge_credits():
    tenant = TenantFactory()
    PlanSubscriptionFactory(tenant=tenant, plan="ai")
    student = UserFactory(role=Role.STUDENT, tenant=tenant)
    grant_initial_credits(student_user=student, amount=5)

    recharge_credits(student_user=student, amount=20, idempotency_key="pack-1")
    balance = student.ai_credit_balance
    assert balance.balance == 25
