"""Tests for fees models and paise money helper."""

import datetime
import pytest
from django.core.exceptions import ValidationError

from apps.fees.helpers.paise import paise_to_rupees_str, rupees_to_paise, financial_year_for
from apps.fees.models import FeeStructure, StudentFeeAssignment

pytestmark = pytest.mark.django_db


def test_paise_math_bankers_rounding():
    # Rupees to Paise rounding (ROUND_HALF_EVEN)
    assert rupees_to_paise(100.55) == 10055
    assert rupees_to_paise("100.55") == 10055
    assert rupees_to_paise("100.555") == 10056
    assert rupees_to_paise("100.565") == 10056  # 565 rounds to even (56)
    assert rupees_to_paise("100.575") == 10058  # 575 rounds to even (58)
    assert rupees_to_paise("0") == 0

    # Paise to Rupees string formatting
    assert paise_to_rupees_str(10055) == "100.55"
    assert paise_to_rupees_str(10056) == "100.56"
    assert paise_to_rupees_str(0) == "0.00"


def test_financial_year_calculation():
    assert financial_year_for(datetime.date(2024, 6, 1)) == "2024-25"
    assert financial_year_for(datetime.date(2025, 3, 31)) == "2024-25"
    assert financial_year_for(datetime.date(2025, 4, 1)) == "2025-26"


def test_fee_structure_total_paise(branch, academic_year):
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        name="Grade 10 General",
        components=[
            {"kind": "tuition", "label": "Tuition", "amount_paise": 5000000, "installment_no": 1},
            {"kind": "transport", "label": "Transport", "amount_paise": 1500000, "installment_no": 1},
        ],
    )
    assert fs.total_paise == 6500000


def test_student_fee_assignment_unique_constraint(branch, academic_year, student_profile):
    fs = FeeStructure.objects.create(
        branch=branch,
        academic_year=academic_year,
        name="Grade 10 General",
    )
    
    StudentFeeAssignment.objects.create(
        student=student_profile,
        fee_structure=fs,
        structure_snapshot=fs.components,
    )
    
    # Attempting to create duplicate assignment should fail
    with pytest.raises(Exception):  # UniqueConstraint IntegrityError
        StudentFeeAssignment.objects.create(
            student=student_profile,
            fee_structure=fs,
            structure_snapshot=fs.components,
        )
