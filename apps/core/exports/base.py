"""Base class for unified export definitions.

Each module creates one subclass per export type. The framework (runner.py)
handles sync/async routing, S3 upload, retry, and cleanup — the module only
defines what to query, what columns to emit, and how to transform each row.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass

from django.conf import settings


def _read_db() -> str:
    return "replica" if "replica" in getattr(settings, "DATABASES", {}) else "default"


@dataclass
class Column:
    key: str           # dict key produced by get_row()
    label: str         # CSV header label
    format: str = "text"  # "text" | "number" | "date" | "currency_paise"


class ExportDefinition(ABC):
    """Abstract base for all export types across the ERP.

    Plain class (not @dataclass) — subclasses set these as class attributes, e.g.
    `allowed_roles = [Role.ADMIN]`. Each list below is class-level; instances must
    not mutate it in place (assign a new list instead) to avoid cross-instance sharing.
    """

    report_type: str        # must match a ReportType enum value
    title: str
    allowed_roles: list = []
    formats: list = ["csv"]  # ["csv"] or ["csv", "pdf"]
    sync_threshold: int = 200  # ≤ this: inline; > this: Celery task

    @abstractmethod
    def get_queryset(self, *, tenant_id, branch_id, params: dict):
        """Return an unevaluated QuerySet filtered by tenant_id (mandatory)."""
        ...

    @abstractmethod
    def get_columns(self, params: dict) -> list[Column]:
        """Return the ordered list of columns for this export."""
        ...

    @abstractmethod
    def get_row(self, instance) -> dict:
        """Transform one ORM instance into a flat dict keyed by Column.key."""
        ...

    def get_filename(self, params: dict) -> str:
        return f"{self.report_type}-export"

    def get_queryset_for_export(self, *, tenant_id, branch_id, params):
        """Return the queryset, directing reads to the replica when available."""
        return self.get_queryset(
            tenant_id=tenant_id, branch_id=branch_id, params=params
        ).using(_read_db())
