"""Money helpers — all amounts are integer paise (F-149). Floats never touch money.

Display uses banker's rounding (ROUND_HALF_EVEN) per EC-FEE-08.
"""

import datetime
from decimal import ROUND_HALF_EVEN, Decimal


def paise_to_rupees_str(paise: int) -> str:
    """Format integer paise as a rupee string with banker's rounding to 2 dp."""
    rupees = (Decimal(int(paise)) / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)
    return f"{rupees:.2f}"


def rupees_to_paise(rupees) -> int:
    """Convert a rupee value (str/Decimal/number) to integer paise, banker's rounding."""
    amount = (Decimal(str(rupees)) * Decimal(100)).quantize(Decimal("1"), rounding=ROUND_HALF_EVEN)
    return int(amount)


def financial_year_for(date: datetime.date) -> str:
    """Indian financial year label for a date (Apr–Mar). e.g. 2024-06-01 → '2024-25'."""
    if date.month >= 4:
        start = date.year
    else:
        start = date.year - 1
    return f"{start}-{str(start + 1)[-2:]}"
