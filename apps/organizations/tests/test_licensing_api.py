"""API tests — platform licensing endpoints + tenant-scoped school dashboards."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.organizations.billing import license_allocator as alloc
from apps.organizations.billing.platform_pricing import unit_price_for_tenant
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    return resp.json().get("data", resp.json())


def _price(tenant):
    return unit_price_for_tenant(tenant.pk)


@pytest.fixture
def platform_owner():
    return UserFactory(
        role=Role.PLATFORM_OWNER, tenant=None, branch=None,
        custom_login_id=None, must_change_password=False,
    )


@pytest.fixture
def tenant():
    return TenantFactory(subdomain="lic-api-school")


@pytest.fixture
def branch(tenant):
    return BranchFactory(tenant=tenant)


def _enroll_students(tenant, branch, n):
    for _ in range(n):
        student = UserFactory(
            role=Role.STUDENT, tenant=tenant, branch=branch,
            custom_login_id=None, phone=None, email=None,
        )
        alloc.on_student_enrolled(student)


def test_overview_kpis(platform_owner, tenant, branch):
    _enroll_students(tenant, branch, 3)
    resp = _client(platform_owner).get(reverse("organizations:platform-licensing-overview"))
    assert resp.status_code == 200
    body = _data(resp)
    assert body["kpis"]["totalUnlicensedStudents"] == 3
    assert body["kpis"]["pendingCollectionsInr"] == 3 * _price(tenant)
    school = next(s for s in body["schools"] if s["tenantId"] == str(tenant.id))
    assert school["unlicensedStudents"] == 3


def test_record_payment_converts_fifo(platform_owner, tenant, branch):
    _enroll_students(tenant, branch, 3)
    resp = _client(platform_owner).post(
        reverse("organizations:platform-licensing-payments"),
        {
            "tenantId": str(tenant.id),
            "licensesGranted": 2,
            "amountInr": 2 * _price(tenant),
            "paymentMode": "upi",
            "referenceNumber": "UPI-123",
        },
        format="json",
    )
    assert resp.status_code == 201
    body = _data(resp)
    assert body["summary"]["licensesConsumed"] == 2
    assert body["summary"]["unlicensedStudents"] == 1

    detail = _data(_client(platform_owner).get(
        reverse("organizations:platform-licensing-tenant-detail", args=[tenant.id]),
    ))
    assert len(detail["unlicensedQueue"]) == 1
    assert len(detail["payments"]) == 1


def test_record_payment_validation(platform_owner, tenant):
    resp = _client(platform_owner).post(
        reverse("organizations:platform-licensing-payments"),
        {"tenantId": str(tenant.id), "licensesGranted": 0, "amountInr": 0},
        format="json",
    )
    assert resp.status_code == 400


def test_renewal_invoice_uses_consumed(platform_owner, tenant, branch):
    client = _client(platform_owner)
    client.post(
        reverse("organizations:platform-licensing-payments"),
        {
            "tenantId": str(tenant.id),
            "licensesGranted": 2,
            "amountInr": 2 * _price(tenant),
            "paymentMode": "cash",
        },
        format="json",
    )
    _enroll_students(tenant, branch, 2)  # consume both

    resp = client.post(
        reverse("organizations:platform-licensing-invoices"),
        {"tenantId": str(tenant.id), "invoiceType": "renewal"},
        format="json",
    )
    assert resp.status_code == 201
    invoice = _data(resp)["invoice"]
    assert invoice["licensesCount"] == 2
    assert invoice["amountInr"] == 2 * _price(tenant)


def test_extend_period_to_june(platform_owner, tenant):
    period = alloc.ensure_period(tenant)
    new_end = f"{period.end_date.year}-06-30"
    resp = _client(platform_owner).patch(
        reverse("organizations:platform-licensing-period", args=[period.id]),
        {"endDate": new_end},
        format="json",
    )
    assert resp.status_code == 200
    assert _data(resp)["period"]["endDate"] == new_end


def test_school_summary_super_admin_and_branch_admin(tenant, branch):
    _enroll_students(tenant, branch, 2)
    other_branch = BranchFactory(tenant=tenant)
    _enroll_students(tenant, other_branch, 1)

    super_admin = UserFactory(
        role=Role.SUPER_ADMIN, tenant=tenant, branch=None,
        custom_login_id=None, must_change_password=False,
    )
    resp = _client(super_admin).get(reverse("organizations:licensing-summary"))
    assert resp.status_code == 200
    body = _data(resp)
    assert body["unlicensedStudents"] == 3
    assert "payments" in body

    admin = UserFactory(
        role=Role.ADMIN, tenant=tenant, branch=branch,
        custom_login_id=None, must_change_password=False,
    )
    resp = _client(admin).get(reverse("organizations:licensing-summary"))
    body = _data(resp)
    assert body["branchUnlicensedStudents"] == 2

    students = _data(_client(admin).get(
        reverse("organizations:licensing-students"), {"status": "unlicensed"},
    ))["students"]
    assert len(students) == 2  # branch-filtered for admins


def test_me_access_blocks_unlicensed_student(tenant, branch):
    student = UserFactory(
        role=Role.STUDENT, tenant=tenant, branch=branch,
        custom_login_id=None, phone=None, email=None, must_change_password=False,
    )
    alloc.on_student_enrolled(student)  # no capacity → unlicensed

    resp = _client(student).get(reverse("accounts:me-access"))
    assert resp.status_code == 200
    body = _data(resp)
    assert body["licenseStatus"] == "unlicensed"
    assert "gallery" in body["blockedModules"]
    assert "fees" not in body["blockedModules"]

    # Payment licenses the student; access opens up.
    alloc.record_payment(tenant, licenses_granted=1, amount_inr=_price(tenant), payment_mode="cash")
    resp = _client(student).get(reverse("accounts:me-access"))
    body = _data(resp)
    assert body["licenseStatus"] == "licensed"
    assert body["blockedModules"] == []


def test_platform_endpoints_forbidden_for_school_roles(tenant):
    super_admin = UserFactory(
        role=Role.SUPER_ADMIN, tenant=tenant, branch=None,
        custom_login_id=None, must_change_password=False,
    )
    resp = _client(super_admin).get(reverse("organizations:platform-licensing-overview"))
    assert resp.status_code == 403
