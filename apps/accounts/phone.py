"""Indian phone normalization — shared by auth, password reset, and User saves."""

import re


def normalize_phone(value: str | None) -> str | None:
    """Normalize Indian mobile numbers to E.164 (+91...). Returns input unchanged if not recognized."""
    if not value:
        return value
    cleaned = re.sub(r"[\s\-]", "", value.strip())
    if cleaned.startswith("+91"):
        return cleaned
    if cleaned.startswith("0") and len(cleaned) == 11:
        return f"+91{cleaned[1:]}"
    if re.fullmatch(r"[6-9]\d{9}", cleaned):
        return f"+91{cleaned}"
    return cleaned


def phone_lookup_values(phone: str) -> list[str]:
    """All stored forms to match against (E.164 + legacy 10-digit)."""
    raw = phone.strip()
    normalized = normalize_phone(raw) or raw
    values = {raw, normalized}
    if normalized.startswith("+91") and len(normalized) == 13:
        values.add(normalized[3:])
    return list(values)
