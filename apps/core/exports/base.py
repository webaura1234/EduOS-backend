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


@dataclass
class FilterSpec:
    key: str
    label: str
    type: str = "text"  # date | date_range | select | number | text | batch_id | exam_id
    required: bool = False
    options_source: str | None = None


class ExportDefinition(ABC):
    """Abstract base for all export types across the ERP.

    Plain class (not @dataclass) — subclasses set these as class attributes, e.g.
    `allowed_roles = [Role.ADMIN]`. Each list below is class-level; instances must
    not mutate it in place (assign a new list instead) to avoid cross-instance sharing.
    """

    report_type: str        # must match a ReportType enum value
    title: str
    allowed_roles: list = []
    formats: list = ["csv"]
    sync_threshold: int = 200  # ≤ this: inline; > this: Celery task

    # Report catalog metadata
    module: str = ""
    description: str = ""
    filters: list = []
    supports_preview: bool = False
    supports_search: bool = False
    default_sort: tuple = ("", "asc")
    estimated_runtime: str = "instant"  # "instant" | "background"
    catalog_visible: bool = True

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

    @property
    def is_aggregation(self) -> bool:
        return isinstance(self, AggregationExportDefinition)


class AggregationExportDefinition(ExportDefinition):
    """Pivot / grouped reports that produce list[dict] rows (not one ORM row each)."""

    @abstractmethod
    def resolve_rows(self, *, tenant, branch, params: dict) -> list[dict]:
        ...

    def get_queryset(self, *, tenant_id, branch_id, params: dict):
        raise NotImplementedError("Aggregation reports use resolve_rows(), not get_queryset().")

    def get_row(self, instance) -> dict:
        raise NotImplementedError("Aggregation reports use resolve_rows(), not get_row().")
