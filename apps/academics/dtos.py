"""Typed response shapes for academics interactors."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class TimetableClashDTO:
    type: str  # faculty | room
    message: str
    entry_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "message": self.message,
            "entryIds": self.entry_ids,
        }


@dataclass
class RolloverStudentPreviewDTO:
    student_id: str
    name: str
    from_class: str
    to_class: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "studentId": self.student_id,
            "name": self.name,
            "fromClass": self.from_class,
            "toClass": self.to_class,
        }


@dataclass
class RolloverPreviewDTO:
    from_year_label: str
    to_year_label: str
    students_to_promote: list[RolloverStudentPreviewDTO]
    warnings: list[str]
    version: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "fromYearLabel": self.from_year_label,
            "toYearLabel": self.to_year_label,
            "studentsToPromote": [s.to_dict() for s in self.students_to_promote],
            "warnings": self.warnings,
            "version": self.version,
        }
