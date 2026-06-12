"""Tests for fees serializers."""

import pytest
from apps.fees.models import FeeInvoice, FeeStructure, Installment
from apps.fees.serializers import FeeInvoiceSerializer, FeeStructureSerializer

pytestmark = pytest.mark.django_db


def test_fee_structure_serializer(branch, academic_year):
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        name="Grade 10 General",
        components=[
            {"kind": "tuition", "label": "Tuition", "amount_paise": 5000000, "installment_no": 1, "due_date": "2024-07-10"},
        ],
    )
    serializer = FeeStructureSerializer(fs)
    data = serializer.data
    
    # Assert camelCase keys
    assert "name" in data
    assert "academicYear" in data
    assert "totalPaise" in data
    assert "createdAt" in data
    assert "updatedAt" in data
    assert data["name"] == "Grade 10 General"
    assert data["totalPaise"] == 5000000


def test_invoice_serializer(branch, student_profile):
    invoice = FeeInvoice.objects.create(
        branch=branch,
        student=student_profile.enrollment,
        total_paise=10000,
        paid_paise=0,
    )
    installment = Installment.objects.create(
        invoice=invoice,
        sequence=1,
        amount_paise=10000,
        paid_paise=0,
        due_date="2024-07-10",
    )
    
    serializer = FeeInvoiceSerializer(invoice)
    data = serializer.data

    assert "totalPaise" in data
    assert "paidPaise" in data
    assert "dueDate" in data
    assert "createdAt" in data
    assert "installments" in data
    assert len(data["installments"]) == 1
    assert data["installments"][0]["sequence"] == 1
    assert data["installments"][0]["amountPaise"] == 10000
