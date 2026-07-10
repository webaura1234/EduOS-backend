"""Concession amount helpers — EC-FEE-07 percent-based rules."""


def concession_amount_paise(concession, *, base_paise: int) -> int:
    """Resolve flat amount on the concession, or derive from rule percent/flat."""
    rule = getattr(concession, "rule", None)
    if rule and rule.percent is not None and base_paise > 0:
        return (int(base_paise) * int(rule.percent)) // 100
    if rule and rule.amount_paise is not None and rule.amount_paise > 0:
        return int(rule.amount_paise)
    amount = int(concession.amount_paise or 0)
    if amount <= 0:
        return 0
    # Percent rules may store placeholder amount_paise=1 until resolved from structure totals.
    if rule and rule.percent and amount == 1 and base_paise > 0:
        return (int(base_paise) * int(rule.percent)) // 100
    return amount


def discount_line_for_request(concession, *, base_paise: int) -> dict:
    label = concession.rule.name if getattr(concession, "rule", None) else "Concession"
    return {
        "request_id": str(concession.id),
        "label": label,
        "amount_paise": concession_amount_paise(concession, base_paise=base_paise),
    }
