"""Auto-map spreadsheet headers onto canonical student-import keys."""

from __future__ import annotations

import re

from apps.admissions.imports.columns import CANONICAL_COLUMNS


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def auto_map_columns(headers: list[str], saved: dict[str, str] | None = None) -> dict[str, str]:
    """Return mapping canonical_key → source header.

    ``saved`` may already map canonical → header; those win when the header still exists.
    """
    mapping: dict[str, str] = {}
    header_by_norm = {_norm(h): h for h in headers}
    used_headers: set[str] = set()

    if saved:
        for key, header in saved.items():
            if header in headers:
                mapping[key] = header
                used_headers.add(header)

    for col in CANONICAL_COLUMNS:
        key = col["key"]
        if key in mapping:
            continue
        for alias in col["aliases"]:
            hit = header_by_norm.get(_norm(alias))
            if hit and hit not in used_headers:
                mapping[key] = hit
                used_headers.add(hit)
                break

    return mapping


def apply_mapping(row: dict[str, str], mapping: dict[str, str]) -> dict[str, str]:
    """Project a raw spreadsheet row onto canonical keys."""
    out: dict[str, str] = {}
    for key, header in mapping.items():
        out[key] = str(row.get(header, "") or "").strip()
    return out
