"""Parity tests for Phase 4 sync CSV export logging."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.analytics.enums import ReportType
from apps.core.exports.registry import get_definition

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


@pytest.fixture
def env():
    from apps.organizations.tests.factories import BranchFactory, TenantFactory

    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch, phone="+919830000099",
        custom_login_id=None, must_change_password=False,
    )
    return dict(tenant=tenant, branch=branch, admin=admin)


def test_exam_class_results_registered_not_in_catalog(env):
    definition = get_definition(ReportType.EXAM_CLASS_RESULTS)
    assert definition.catalog_visible is False
    assert definition.report_type == ReportType.EXAM_CLASS_RESULTS

    resp = _client(env["admin"]).get(reverse("analytics:report-catalog"))
    assert resp.status_code == 200
    body = resp.json().get("data", resp.json())
    ids = {r["id"] for r in body["reports"]}
    assert ReportType.EXAM_CLASS_RESULTS not in ids
    assert ReportType.COLLEGE_NAAC not in ids
    assert ReportType.COLLEGE_NIRF not in ids
