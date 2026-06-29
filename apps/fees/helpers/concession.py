"""Concession amount helpers — EC-FEE-07 percent-based rules."""


def concession_amount_paise(request, *, base_paise: int) -> int:
    """Resolve flat amount_paise on the request, or derive from rule percent."""
    if request.amount_paise and request.amount_paise > 0:
        return int(request.amount_paise)
    rule = getattr(request, "rule", None)
    if rule and rule.percent and base_paise > 0:
        return (int(base_paise) * int(rule.percent)) // 100
    return 0


def discount_line_for_request(request, *, base_paise: int) -> dict:
    label = request.rule.name if getattr(request, "rule", None) else "Concession"
    return {
        "request_id": str(request.id),
        "label": label,
        "amount_paise": concession_amount_paise(request, base_paise=base_paise),
    }
