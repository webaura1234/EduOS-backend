"""Admin Payments screen — the paginated/filterable endpoint that replaced the
unbounded ``payments`` field on AdminFeesOverviewView."""

import datetime

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from apps.fees.enums import PaymentMethod
from apps.fees.interactors import (
    CreatePaymentOrderInteractor,
    RecordOfflinePaymentInteractor,
    VerifyPaymentCaptureInteractor,
    generate_invoices_for_batch,
)
from apps.fees.models import FeeStructure
from apps.accounts.tokens import generate_access_token

pytestmark = pytest.mark.django_db


def _client(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {generate_access_token(user)}")
    return c


def _data(resp):
    body = resp.json()
    return body.get("data", body)


def _capture_online_payment(*, invoice, student_profile, amount_paise, key):
    payment = CreatePaymentOrderInteractor(
        invoice_id=invoice.id, amount_paise=amount_paise, method=PaymentMethod.RAZORPAY,
        payer_user=student_profile.user, idempotency_key=key,
    ).execute()
    return VerifyPaymentCaptureInteractor(
        payment_id=payment.id, razorpay_payment_id=f"pay_{key}",
    ).execute()


@pytest.fixture
def two_invoices(branch, batch, academic_year, student_profile, admin):
    fs = FeeStructure.objects.create(
        branch=branch, academic_year=academic_year, name="Grade 10",
        components=[{"kind": "tuition", "label": "Tuition", "amount_paise": 500000,
                     "installment_no": 1, "due_date": "2024-07-10"}],
    )
    invoices = generate_invoices_for_batch(
        branch=branch, batch_id=batch.id, academic_year=academic_year, fee_structure=fs,
    )
    return invoices[0], student_profile


def test_payments_list_is_paginated_and_excludes_from_overview(two_invoices, admin):
    invoice, student_profile = two_invoices
    _capture_online_payment(invoice=invoice, student_profile=student_profile, amount_paise=200000, key="p1")
    RecordOfflinePaymentInteractor(
        invoice_id=invoice.id, amount_paise=300000, method="cash", payer_user=student_profile.user, user=admin,
    ).execute()

    resp = _client(admin).get(reverse("fees:admin-payments-list"))
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert set(body.keys()) == {"count", "next", "previous", "results"}
    assert body["count"] == 2
    assert len(body["results"]) == 2
    row = body["results"][0]
    assert set(row.keys()) == {
        "id", "studentId", "studentName", "classLabel", "paidAt", "amount", "amountPaise",
        "method", "reference", "receiptNo", "orderId", "status", "source", "invoiceId",
    }

    overview = _client(admin).get(reverse("fees:admin-overview"))
    assert "payments" not in _data(overview)


def test_payments_list_filters_by_status_and_page_size(two_invoices, admin):
    invoice, student_profile = two_invoices
    _capture_online_payment(invoice=invoice, student_profile=student_profile, amount_paise=100000, key="cap1")
    RecordOfflinePaymentInteractor(
        invoice_id=invoice.id, amount_paise=100000, method="cash", payer_user=student_profile.user, user=admin,
    ).execute()

    resp = _client(admin).get(reverse("fees:admin-payments-list"), {"status": "captured"})
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert body["count"] == 2  # both online capture and offline record land as "captured"
    assert all(r["status"] == "captured" for r in body["results"])

    resp2 = _client(admin).get(reverse("fees:admin-payments-list"), {"page_size": 1})
    assert _data(resp2)["count"] == 2
    assert len(_data(resp2)["results"]) == 1
    assert _data(resp2)["next"] is not None


def test_payments_list_filters_by_date_range(two_invoices, admin):
    invoice, student_profile = two_invoices
    payment = _capture_online_payment(
        invoice=invoice, student_profile=student_profile, amount_paise=100000, key="dated",
    )
    old_date = datetime.datetime(2020, 1, 1, tzinfo=datetime.timezone.utc)
    payment.captured_at = old_date
    payment.save(update_fields=["captured_at"])

    resp_out_of_range = _client(admin).get(
        reverse("fees:admin-payments-list"),
        {"date_from": "2026-01-01", "date_to": "2026-12-31"},
    )
    assert _data(resp_out_of_range)["count"] == 0

    resp_in_range = _client(admin).get(
        reverse("fees:admin-payments-list"),
        {"date_from": "2020-01-01", "date_to": "2020-01-31"},
    )
    assert _data(resp_in_range)["count"] == 1


def test_payments_date_filter_uses_utc_calendar_day_not_server_local_tz(two_invoices, admin):
    """The server's TIME_ZONE (Asia/Kolkata, UTC+5:30) must not shift which day a
    payment is bucketed into — a payment captured late in the UTC day (e.g.
    20:50 UTC, already the next calendar day in IST) must still count toward its
    UTC day, matching how "day" was always computed (a plain .date() on the
    UTC-aware datetime Django returns), not the server-local calendar day."""
    invoice, student_profile = two_invoices
    payment = _capture_online_payment(
        invoice=invoice, student_profile=student_profile, amount_paise=100000, key="tzedge",
    )
    late_utc = datetime.datetime(2026, 6, 29, 20, 50, 0, tzinfo=datetime.timezone.utc)
    payment.captured_at = late_utc
    payment.save(update_fields=["captured_at"])

    resp_utc_day = _client(admin).get(
        reverse("fees:admin-payments-list"), {"date_from": "2026-06-29", "date_to": "2026-06-29"},
    )
    assert _data(resp_utc_day)["count"] == 1

    resp_next_local_day = _client(admin).get(
        reverse("fees:admin-payments-list"), {"date_from": "2026-06-30", "date_to": "2026-06-30"},
    )
    assert _data(resp_next_local_day)["count"] == 0


def test_payments_list_filters_by_student_id(two_invoices, admin, student_profile):
    invoice, sp = two_invoices
    _capture_online_payment(invoice=invoice, student_profile=sp, amount_paise=100000, key="stu1")

    resp = _client(admin).get(reverse("fees:admin-payments-list"), {"studentId": str(student_profile.id)})
    assert _data(resp)["count"] == 1

    resp_wrong = _client(admin).get(
        reverse("fees:admin-payments-list"), {"studentId": "00000000-0000-0000-0000-000000000000"},
    )
    assert _data(resp_wrong)["count"] == 0


def test_payments_summary_matches_list(two_invoices, admin):
    invoice, student_profile = two_invoices
    _capture_online_payment(invoice=invoice, student_profile=student_profile, amount_paise=200000, key="sum1")
    RecordOfflinePaymentInteractor(
        invoice_id=invoice.id, amount_paise=300000, method="cash", payer_user=student_profile.user, user=admin,
    ).execute()

    resp = _client(admin).get(reverse("fees:admin-payments-summary"), {"status": "captured"})
    assert resp.status_code == 200, resp.content
    body = _data(resp)
    assert body["count"] == 2
    assert body["totalPaise"] == 500000
    assert body["methodBreakdown"]["online"] == 1
    assert body["methodBreakdown"]["cash"] == 1
