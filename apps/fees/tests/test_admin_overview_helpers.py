"""Tests for admin overview helpers."""

from apps.fees.views.admin_overview import _batch_label, _derive_installments_from_components, _PAY_METHOD


def test_derive_installments_from_components():
    components = [
        {"label": "Tuition", "amount_paise": 500000, "due_date": "2026-07-10", "installment_no": 1},
        {"label": "Transport", "amount_paise": 100000, "due_date": "2026-09-10", "installment_no": 2},
    ]
    rows = _derive_installments_from_components(components)
    assert len(rows) == 2
    assert rows[0]["label"] == "Tuition"
    assert rows[0]["dueDate"] == "2026-07-10"
    assert rows[0]["amount"] == 5000.0
    assert rows[1]["amount"] == 1000.0


def test_razorpay_maps_to_upi_for_display():
    assert _PAY_METHOD["razorpay"] == "upi"
    assert _PAY_METHOD["bank_transfer"] == "upi"


def test_batch_label_includes_course_and_section():
    class _Course:
        name = "Class 10"

    class _Batch:
        name = "A"
        course = _Course()

    assert _batch_label(_Batch()) == "Class 10 - A"
