"""Global registry mapping report_type → ExportDefinition.

Each module registers its definitions in its own exports.py, called from AppConfig.ready().
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from apps.core.exports.base import ExportDefinition

_REGISTRY: dict[str, "ExportDefinition"] = {}


def register(definition: "ExportDefinition") -> None:
    _REGISTRY[definition.report_type] = definition


def get_definition(report_type: str) -> "ExportDefinition":
    if report_type not in _REGISTRY:
        raise ValueError(f"No ExportDefinition registered for report_type={report_type!r}")
    return _REGISTRY[report_type]


def all_definitions() -> dict[str, "ExportDefinition"]:
    return dict(_REGISTRY)
