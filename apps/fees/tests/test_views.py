"""End-to-end views tests for the fees app."""

import hmac
import hashlib
import json
import pytest
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.accounts.models.user import Role
from apps.accounts.tests.factories import UserFactory
from apps.accounts.tokens import generate_access_token
from apps.fees.enums import PaymentMethod, PaymentStatus
from apps.fees.models import FeeInvoice, FeeStructure, Payment, ConcessionRule, ConcessionRequest, Refund, CreditNote
from apps.fees.interactors import generate_invoices_for_batch
from apps.organizations.tests.factories import BranchFactory, TenantFactory

pytestmark = pytest.mark.django_db


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def test_fee_structure_api_lifecycle(admin_client, branch, academic_year):
    url = reverse("fees:structures-list")
    
    # Create
    payload = {
        "name": "Class 10 General",
        "academicYear": str(academic_year.id),
        "components": [
            {"kind": "tuition", "label": "Tuition", "amount_paise": 6000000, "installment_no": 1, "due_date": "2024-07-10"},
        ],
    }
    
    resp = admin_client.post(url, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.content
    
    # List (paginated by StandardPagination)
    resp = admin_client.get(url, {"branchId": str(branch.id)})
    assert resp.status_code == status.HTTP_200_OK
    listing = _data(resp)
    assert len(listing["results"]) == 1
    assert listing["results"][0]["name"] == "Class 10 General"


def test_generate_invoices_api(admin_client, branch, batch, academic_year, student_profile):
    # Create structure
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        name="Grade 10 General",
        components=[
            {"kind": "tuition", "label": "Tuition", "amount_paise": 5000000, "installment_no": 1, "due_date": "2024-07-10"},
        ],
    )
    
    url = reverse("fees:invoices-generate")
    payload = {
        "batchId": str(batch.id),
        "feeStructureId": str(fs.id),
        "academicYearId": str(academic_year.id),
        "branchId": str(branch.id),
    }
    
    resp = admin_client.post(url, payload, format="json")
    assert resp.status_code == status.HTTP_201_CREATED, resp.content
    assert FeeInvoice.objects.filter(student=student_profile).count() == 1


def test_student_and_parent_portal_dues(student_client, parent_client, student_profile, parent_user, guardian_link, branch, academic_year, batch):
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 5000, "installment_no": 1, "due_date": "2024-07-10"}],
    )
    invoice = generate_invoices_for_batch(branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs)[0]

    # Student portal
    resp = student_client.get(reverse("fees:student-dues"))
    assert resp.status_code == 200
    dues = _data(resp)
    assert len(dues) == 1
    assert dues[0]["id"] == str(invoice.id)

    # Parent portal (linked child)
    # conftest.py defines parent_client linked to student_profile via guardian_link
    resp = parent_client.get(reverse("fees:parent-child-dues", kwargs={"student_id": str(student_profile.user.id)}))
    assert resp.status_code == 200
    p_dues = _data(resp)
    assert len(p_dues) == 1
    assert p_dues[0]["id"] == str(invoice.id)

    # Parent portal (unlinked student)
    unlinked_student = UserFactory(role=Role.STUDENT, tenant=branch.tenant, branch=branch, custom_login_id="STU-UNLINKED")
    resp = parent_client.get(reverse("fees:parent-child-dues", kwargs={"student_id": str(unlinked_student.id)}))
    assert resp.status_code == 403


def test_payments_api_verify_capture(student_client, student_profile, branch, academic_year, batch):
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 5000, "installment_no": 1, "due_date": "2024-07-10"}],
    )
    invoice = generate_invoices_for_batch(branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs)[0]

    # Create order
    resp = student_client.post(reverse("fees:orders"), {
        "invoiceId": str(invoice.id),
        "amountPaise": 5000,
        "idempotencyKey": "order-key-1",
    }, format="json")
    assert resp.status_code == 201
    order_id = _data(resp)["razorpayOrderId"]

    # Verify capture
    resp = student_client.post(reverse("fees:payments-verify"), {
        "razorpayPaymentId": "pay_sandbox_verify_1",
        "razorpayOrderId": order_id,
        "razorpaySignature": "sandbox_sig_placeholder",
    }, format="json")
    assert resp.status_code == 200
    assert _data(resp)["status"] == "captured"


def test_offline_payment_api(admin_client, student_profile, branch, academic_year, batch):
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 5000, "installment_no": 1, "due_date": "2024-07-10"}],
    )
    invoice = generate_invoices_for_batch(branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs)[0]

    resp = admin_client.post(reverse("fees:payments-offline"), {
        "invoiceId": str(invoice.id),
        "studentId": str(student_profile.id),
        "amountPaise": 5000,
        "method": "cash",
        "branchId": str(branch.id),
    }, format="json")
    assert resp.status_code == 201
    assert _data(resp)["status"] == "captured"


def test_razorpay_webhook_api(student_profile, branch, academic_year, batch):
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 5000, "installment_no": 1, "due_date": "2024-07-10"}],
    )
    invoice = generate_invoices_for_batch(branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs)[0]

    # Create payment first so webhook finds it
    payment = Payment.objects.create(
        invoice=invoice,
        amount_paise=5000,
        method="razorpay",
        status=PaymentStatus.PENDING,
        razorpay_order_id="order_webhook_1",
        idempotency_key="webhook-key-1",
    )

    client = APIClient()
    payload = {
        "id": "evt_webhook_1",
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_sandbox_web_1",
                    "order_id": "order_webhook_1",
                    "status": "captured",
                }
            }
        }
    }
    body = json.dumps(payload, separators=(",", ":")).encode()
    
    # Calculate HMAC using secret configured in settings (dev has "sandbox_webhook_secret")
    sig = hmac.new(b"sandbox_webhook_secret", body, hashlib.sha256).hexdigest()

    resp = client.post(reverse("fees:webhook"), payload, format="json", HTTP_X_RAZORPAY_SIGNATURE=sig)
    assert resp.status_code == 200
    payment.refresh_from_db()
    assert payment.status == "captured"
