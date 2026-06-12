"""Examinations API permissions."""

from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.attendance.permissions import IsFacultyOrAdmin

__all__ = ["IsAdminOrSuperAdmin", "IsFacultyOrAdmin"]
