"""Download filename helpers for report exports."""

import re
from datetime import datetime


def _slug(value: str) -> str:
    text = re.sub(r"[^\w.\-]+", "-", str(value).strip(), flags=re.UNICODE)
    text = re.sub(r"-{2,}", "-", text).strip("-._")
    return text or "export"


def build_download_filename(definition, *, export, params=None) -> str:
    """Build a Content-Disposition filename from definition + branch + date."""
    params = params if params is not None else (export.params or {})
    try:
        base = definition.get_filename(params) if definition is not None else None
    except Exception:  # noqa: BLE001
        base = None
    if not base:
        base = f"{export.report_type}-export"

    parts = [_slug(base.removesuffix(".csv"))]

    branch = getattr(export, "branch", None)
    branch_name = getattr(branch, "name", None) if branch is not None else None
    if branch_name:
        parts.append(_slug(branch_name))

    created = getattr(export, "created_at", None)
    if isinstance(created, datetime):
        parts.append(created.date().isoformat())
    else:
        parts.append(datetime.utcnow().date().isoformat())

    return f"{'_'.join(parts)}.csv"
