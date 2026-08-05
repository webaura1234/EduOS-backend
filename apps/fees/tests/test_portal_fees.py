"""Tests for student/parent portal fees payload helpers."""

from types import SimpleNamespace
from uuid import uuid4

from apps.fees.interactors.portal_fees import _concession_breakdown


def _assignment(*, snap_components, discount_lines=None):
    return SimpleNamespace(
        pk=uuid4(),
        structure_snapshot=snap_components,
        discount_lines=discount_lines or [],
    )


def test_concession_breakdown_uses_structure_once_for_matching_invoice():
    assignment = _assignment(
        snap_components=[
            {"amount_paise": 5000000},
            {"amount_paise": 1000000},
        ],
        discount_lines=[{"label": "Merit", "amount_paise": 500000}],
    )
    invoice = SimpleNamespace(total_paise=5500000, assignment=assignment)

    result = _concession_breakdown([invoice])

    assert result["grossDue"] == 60000.0
    assert result["concessionTotal"] == 5000.0
    assert len(result["concessions"]) == 1
    assert result["concessions"][0]["label"] == "Merit"


def test_concession_breakdown_does_not_inflate_opening_balance_from_full_snapshot():
    assignment = _assignment(
        snap_components=[
            {"amount_paise": 5000000},
            {"amount_paise": 1000000},
        ],
        discount_lines=[{"label": "Merit", "amount_paise": 500000}],
    )
    # Opening-balance invoice amount ≠ structure net — must not use full snapshot as Original fee.
    opening = SimpleNamespace(total_paise=1200000, assignment=assignment)

    result = _concession_breakdown([opening])

    assert result["grossDue"] == 12000.0
    assert result["concessionTotal"] == 0.0
    assert result["concessions"] == []


def test_concession_breakdown_dedupes_assignment_across_invoices():
    assignment = _assignment(
        snap_components=[{"amount_paise": 6000000}],
        discount_lines=[],
    )
    tuition = SimpleNamespace(total_paise=6000000, assignment=assignment)
    extra = SimpleNamespace(total_paise=1500000, assignment=assignment)

    result = _concession_breakdown([tuition, extra])

    # Structure counted once; extra invoice adds only its face value.
    assert result["grossDue"] == 75000.0
    assert result["concessionTotal"] == 0.0
