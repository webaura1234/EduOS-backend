"""Cross-tenant IDOR regression tests for the fee payment endpoints.

Confirmed vulnerability (see audit): CreateOrderView / RecordOfflinePaymentView /
VerifyPaymentCaptureView resolved invoices, students, and payments by primary key
alone, with no tenant/branch/ownership check anywhere in the call chain. Any
authenticated user who obtained or guessed another tenant's invoice/payment UUID
could create or verify a payment against it. These tests assert the fix holds.
"""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.academics.models import AcademicYear, Batch, Course, Department
from apps.accounts.models.profile import AcademicStatus, StudentProfile
from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.admissions.queries.enrollment import resolve_enrollment_for_profile
from apps.fees.enums import PaymentMethod
from apps.fees.models import FeeInvoice, Payment
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
def other_tenant_invoice(tenant, branch):
    """An invoice + its owning student, in a completely different tenant than
    the shared `tenant`/`branch`/`admin`/`student_user` conftest fixtures."""
    other_tenant = TenantFactory(institution_type="school")
    other_branch = BranchFactory(tenant=other_tenant)
    other_year = AcademicYear.objects.create(
        branch=other_branch, name="2024-25", is_current=True,
        start_date=datetime.date(2024, 6, 1), end_date=datetime.date(2025, 4, 30),
    )
    other_dept = Department.objects.create(branch=other_branch, name="Dept", department_type="academic")
    other_course = Course.objects.create(department=other_dept, name="Course")
    other_batch = Batch.objects.create(course=other_course, academic_year=other_year, name="Section")

    other_student_user = UserFactory(
        role=Role.STUDENT, tenant=other_tenant, branch=other_branch,
        custom_login_id="OTHER-STU-1", must_change_password=False,
    )
    other_profile = StudentProfile.objects.create(
        user=other_student_user, current_batch=other_batch, academic_status=AcademicStatus.ACTIVE,
    )
    other_enrollment = resolve_enrollment_for_profile(other_profile)
    invoice = FeeInvoice.objects.create(
        branch=other_branch, student=other_enrollment, total_paise=50000, paid_paise=0,
    )
    return dict(tenant=other_tenant, branch=other_branch, student_user=other_student_user,
               enrollment=other_enrollment, invoice=invoice)


def test_student_cannot_create_order_for_another_tenants_invoice(student_client, other_tenant_invoice):
    resp = student_client.post(reverse("fees:orders"), {
        "invoiceId": str(other_tenant_invoice["invoice"].id),
        "amountPaise": 10000,
        "idempotencyKey": "attack-key-1",
    }, format="json")
    assert resp.status_code == 400, resp.content
    assert Payment.objects.filter(invoice=other_tenant_invoice["invoice"]).count() == 0


def test_student_cannot_create_order_for_classmates_invoice(student_client, tenant, branch, batch):
    other_student_user = UserFactory(
        role=Role.STUDENT, tenant=tenant, branch=branch,
        custom_login_id="STU-002", must_change_password=False,
    )
    other_profile = StudentProfile.objects.create(
        user=other_student_user, current_batch=batch, academic_status=AcademicStatus.ACTIVE,
    )
    other_enrollment = resolve_enrollment_for_profile(other_profile)
    invoice = FeeInvoice.objects.create(branch=branch, student=other_enrollment, total_paise=50000, paid_paise=0)

    resp = student_client.post(reverse("fees:orders"), {
        "invoiceId": str(invoice.id),
        "amountPaise": 10000,
        "idempotencyKey": "attack-key-2",
    }, format="json")
    assert resp.status_code == 400, resp.content
    assert Payment.objects.filter(invoice=invoice).count() == 0


def test_student_can_still_create_order_for_own_invoice(student_client, student_profile, branch):
    invoice = FeeInvoice.objects.create(
        branch=branch, student=student_profile.enrollment, total_paise=50000, paid_paise=0,
    )
    resp = student_client.post(reverse("fees:orders"), {
        "invoiceId": str(invoice.id),
        "amountPaise": 10000,
        "idempotencyKey": "legit-key-1",
    }, format="json")
    assert resp.status_code == 201, resp.content


def test_admin_cannot_record_offline_payment_for_another_tenants_invoice(admin_client, other_tenant_invoice):
    resp = admin_client.post(reverse("fees:payments-offline"), {
        "invoiceId": str(other_tenant_invoice["invoice"].id),
        "amountPaise": 10000,
        "method": PaymentMethod.CASH,
        "studentId": str(other_tenant_invoice["enrollment"].student_profile_id),
    }, format="json")
    assert resp.status_code == 400, resp.content
    assert Payment.objects.filter(invoice=other_tenant_invoice["invoice"]).count() == 0


def test_admin_cannot_record_offline_payment_with_mismatched_student_and_invoice(
    admin_client, tenant, branch, batch, student_profile,
):
    """The invoice must actually belong to the given studentId, not just be in-branch."""
    other_student_user = UserFactory(
        role=Role.STUDENT, tenant=tenant, branch=branch,
        custom_login_id="STU-003", must_change_password=False,
    )
    other_profile = StudentProfile.objects.create(
        user=other_student_user, current_batch=batch, academic_status=AcademicStatus.ACTIVE,
    )
    other_enrollment = resolve_enrollment_for_profile(other_profile)
    invoice = FeeInvoice.objects.create(branch=branch, student=other_enrollment, total_paise=50000, paid_paise=0)

    resp = admin_client.post(reverse("fees:payments-offline"), {
        "invoiceId": str(invoice.id),
        "amountPaise": 10000,
        "method": PaymentMethod.CASH,
        "studentId": str(student_profile.pk),  # a DIFFERENT student than the invoice's owner
    }, format="json")
    assert resp.status_code == 400, resp.content
    assert Payment.objects.filter(invoice=invoice).count() == 0


def test_verify_capture_rejects_another_tenants_payment(student_client, other_tenant_invoice):
    other_payment = Payment.objects.create(
        invoice=other_tenant_invoice["invoice"], amount_paise=10000,
        method=PaymentMethod.RAZORPAY, payer=other_tenant_invoice["student_user"],
        idempotency_key="other-tenant-payment-1", razorpay_order_id="order_other_1",
    )
    resp = student_client.post(reverse("fees:payments-verify"), {
        "paymentId": str(other_payment.id),
        "razorpayPaymentId": "pay_fake_1",
        "razorpayOrderId": "order_other_1",
        "razorpaySignature": "sig_fake_1",
    }, format="json")
    assert resp.status_code == 400, resp.content
    other_payment.refresh_from_db()
    assert other_payment.status != "captured"
