"""Admin Fees overview aggregate — FeesData shape."""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.models.profile import StudentProfile
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.tests.factories import StudentEnrollmentFactory
from apps.fees.models.invoice import FeeInvoice
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


@pytest.fixture
def env():
    tenant = TenantFactory(institution_type="school")
    branch = BranchFactory(tenant=tenant)
    admin = UserFactory(role=Role.ADMIN, tenant=tenant, branch=branch,
                        phone="+919810000001", custom_login_id=None,
                        must_change_password=False)
    return dict(tenant=tenant, branch=branch, admin=admin)


def test_overview_shape(env):
    resp = _client(env["admin"]).get(reverse("fees:admin-overview"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    for key in ("institutionType", "structures", "concessionRules", "concessionRequests",
                "payments", "creditNotes", "creditNoteRequests", "examFeeInvoices",
                "ledger", "collection", "refunds", "webhooks", "reconciliation",
                "installmentSchedulesByStudent", "batches", "currentAcademicYearId"):
        assert key in body, f"missing {key}"
    assert set(body["collection"]) == {
        "collectedToday", "collectedThisMonth", "outstandingTotal", "overdueCount", "updatedAt",
    }


def test_ledger_reflects_outstanding_invoice(env):
    student = UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
                          custom_login_id="STU-1", first_name="Ravi",
                          must_change_password=False)
    profile = StudentProfile.objects.create(user=student)
    enrollment = StudentEnrollmentFactory(student_profile=profile, branch=env["branch"])
    FeeInvoice.objects.create(branch=env["branch"], student=enrollment,
                              total_paise=500000, paid_paise=200000)

    body = _data(_client(env["admin"]).get(reverse("fees:admin-overview")))
    row = next(r for r in body["ledger"] if r["studentName"].startswith("Ravi"))
    assert row["totalDue"] == 5000.0
    assert row["paid"] == 2000.0
    assert row["balance"] == 3000.0
    assert body["collection"]["outstandingTotal"] == 3000.0


def test_record_payment_by_student_allocates_to_open_invoice(env):
    student = UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
                          custom_login_id="STU-PAY", first_name="Meera",
                          must_change_password=False)
    profile = StudentProfile.objects.create(user=student)
    enrollment = StudentEnrollmentFactory(student_profile=profile, branch=env["branch"])
    FeeInvoice.objects.create(branch=env["branch"], student=enrollment,
                              total_paise=500000, paid_paise=0)

    resp = _client(env["admin"]).post(
        reverse("fees:offline-by-student"),
        {"studentId": str(profile.id), "amountPaise": 300000, "method": "cash"},
        format="json",
    )
    assert resp.status_code == 201, resp.content
    # Ledger now shows ₹3000 paid against the ₹5000 due.
    body = _data(_client(env["admin"]).get(reverse("fees:admin-overview")))
    row = next(r for r in body["ledger"] if r["studentName"].startswith("Meera"))
    assert row["paid"] == 3000.0
    assert row["balance"] == 2000.0


def test_requires_admin(env):
    student = UserFactory(role=Role.STUDENT, tenant=env["tenant"], branch=env["branch"],
                          custom_login_id="STU-2", must_change_password=False)
    resp = _client(student).get(reverse("fees:admin-overview"))
    assert resp.status_code == 403
