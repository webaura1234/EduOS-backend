"""Academics API permissions — reuses shared role checks."""

from apps.accounts.permissions import IsAdminOrSuperAdmin

__all__ = ["IsAdminOrSuperAdmin"]
