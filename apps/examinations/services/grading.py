"""Grading helpers — percentage, grade bands, SGPA, grace marks, banker's rounding."""

from __future__ import annotations

import hashlib
import json
from decimal import ROUND_HALF_EVEN, Decimal
from typing import Any


def bankers_round(value, *, places: int = 2) -> Decimal:
    quant = Decimal("1") if places == 0 else Decimal("0." + "0" * (places - 1) + "1")
    return Decimal(str(value)).quantize(quant, rounding=ROUND_HALF_EVEN)


def percent_of(obtained, max_marks) -> Decimal | None:
    if obtained is None or max_marks is None or Decimal(str(max_marks)) <= 0:
        return None
    return bankers_round(Decimal(str(obtained)) / Decimal(str(max_marks)) * 100)


def lookup_grade(bands: list[dict], percent: Decimal) -> tuple[str, Decimal | None]:
    pct = float(percent)
    for band in bands:
        min_p = float(band.get("min_percent", band.get("minPercent", 0)))
        max_p = float(band.get("max_percent", band.get("maxPercent", 100)))
        if min_p <= pct <= max_p:
            grade = str(band.get("grade", ""))
            gp = band.get("grade_point", band.get("gradePoint"))
            return grade, bankers_round(gp, places=2) if gp is not None else None
    return "", None


def scaled_pass_marks(subject_pass_marks: int, subject_max_marks: int, slot_max_marks) -> Decimal:
    if subject_max_marks <= 0:
        return bankers_round(subject_pass_marks)
    ratio = Decimal(str(slot_max_marks)) / Decimal(str(subject_max_marks))
    return bankers_round(Decimal(subject_pass_marks) * ratio)


def compute_grace(
    *,
    marks: Decimal,
    max_marks: Decimal,
    grace_max: int,
    pass_percent: Decimal,
) -> tuple[Decimal, Decimal]:
    """Return (final_marks, grace_applied) to reach pass threshold up to grace_max."""
    if max_marks <= 0:
        return marks, Decimal("0")
    current_pct = marks / max_marks * 100
    if current_pct >= pass_percent:
        return marks, Decimal("0")
    needed = (pass_percent / 100 * max_marks) - marks
    needed = bankers_round(max(Decimal("0"), needed), places=2)
    grace = min(Decimal(grace_max), needed)
    return bankers_round(marks + grace), grace


def compute_sgpa(
    subject_rows: list[dict],
    *,
    exclude_absent: bool = True,
) -> Decimal | None:
    """College SGPA from [{grade_point, credits, is_absent}]."""
    total_points = Decimal("0")
    total_credits = Decimal("0")
    for row in subject_rows:
        if row.get("is_absent") and exclude_absent:
            continue
        gp = row.get("grade_point")
        credits = row.get("credits")
        if gp is None or not credits:
            continue
        total_points += Decimal(str(gp)) * Decimal(str(credits))
        total_credits += Decimal(str(credits))
    if total_credits <= 0:
        return None
    return bankers_round(total_points / total_credits)


def compute_overall_percent(subject_percents: list[Decimal | None]) -> Decimal:
    valid = [p for p in subject_percents if p is not None]
    if not valid:
        return Decimal("0")
    return bankers_round(sum(valid) / len(valid))


def snapshot_hash(entries: list[dict[str, Any]]) -> str:
    """Deterministic sha256 of frozen marks payload at publish time."""
    payload = json.dumps(sorted(entries, key=lambda e: (e["student_id"], e["subject_id"])), sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
