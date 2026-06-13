"""Payroll computation — pure functions. Money is integer paise; banker's rounding.

No ORM here: the interactor passes the employee's component snapshot and the set of
holiday dates for the month; this service computes working days, pro-rata, and totals.
"""

import calendar
import datetime
from decimal import ROUND_HALF_EVEN, Decimal


def _month_bounds(period_month: datetime.date):
    last = calendar.monthrange(period_month.year, period_month.month)[1]
    return period_month.replace(day=1), datetime.date(period_month.year, period_month.month, last)


def _working_days(start: datetime.date, end: datetime.date, holidays: set) -> int:
    """Count days that are not Sunday and not a holiday in [start, end] inclusive."""
    if end < start:
        return 0
    days = 0
    d = start
    while d <= end:
        if d.weekday() != 6 and d not in holidays:  # 6 == Sunday
            days += 1
        d += datetime.timedelta(days=1)
    return days


def working_days_between(start: datetime.date, end: datetime.date, holiday_dates) -> int:
    """Public: count working days (non-Sunday, non-holiday) in [start, end] inclusive."""
    return _working_days(start, end, set(holiday_dates or []))


def _round_paise(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_EVEN))


def _basic_paise(components: list) -> int:
    for c in components:
        if c.get("kind") == "earning" and str(c.get("name", "")).strip().lower() == "basic":
            return int(c.get("amountPaise", 0))
    # Fallback: first earning.
    for c in components:
        if c.get("kind") == "earning":
            return int(c.get("amountPaise", 0))
    return 0


def _resolve_lines(components: list) -> list:
    """Turn a component snapshot into resolved {name, kind, amountPaise} lines (full month)."""
    basic = Decimal(_basic_paise(components))
    lines = []
    for c in components:
        calc = c.get("calc", "fixed")
        if calc == "percent_of_basic":
            amt = _round_paise(basic * Decimal(str(c.get("percent", 0))) / Decimal(100))
        else:
            amt = int(c.get("amountPaise", 0))
        lines.append({"name": c.get("name", ""), "kind": c.get("kind", "earning"),
                      "amountPaise": amt})
    return lines


def compute_for_employee(*, components, period_month, holiday_dates, joined_at, exited_at):
    """Compute a payslip dict for one employee. Pure; returns a dict ready to persist."""
    month_start, month_end = _month_bounds(period_month)
    holidays = set(holiday_dates or [])

    payable_days = _working_days(month_start, month_end, holidays)
    active_start = max(month_start, joined_at) if joined_at else month_start
    active_end = min(month_end, exited_at) if exited_at else month_end
    worked_days = _working_days(active_start, active_end, holidays)

    factor = (Decimal(worked_days) / Decimal(payable_days)) if payable_days else Decimal(0)
    pro_rated = worked_days < payable_days

    full_lines = _resolve_lines(components)
    lines = []
    gross = 0
    deductions = 0
    for ln in full_lines:
        amt = _round_paise(Decimal(ln["amountPaise"]) * factor) if pro_rated else ln["amountPaise"]
        out = {**ln, "amountPaise": amt}
        lines.append(out)
        if ln["kind"] == "earning":
            gross += amt
        else:
            deductions += amt

    return {
        "components": lines,
        "gross_paise": gross,
        "deductions_paise": deductions,
        "net_paise": gross - deductions,
        "worked_days": Decimal(worked_days),
        "payable_days": Decimal(payable_days),
        "pro_rated": pro_rated,
    }
