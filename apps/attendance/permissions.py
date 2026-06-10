"""Attendance permissions."""

from rest_framework.permissions import BasePermission

from apps.accounts.models.user import Role


class IsFacultyOrAdmin(BasePermission):
    """Faculty (who mark) or admin/super-admin (who oversee)."""
    message = "Faculty or admin access required."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role in {Role.FACULTY, Role.ADMIN, Role.SUPER_ADMIN}
        )
