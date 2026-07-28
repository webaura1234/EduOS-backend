"""DRF permissions for analytics report exports."""

from rest_framework.permissions import BasePermission

from apps.accounts.models.user import Role

REPORT_DOWNLOADED = "report.downloaded"


def user_can_access_export(user, export) -> bool:
    """Return True if ``user`` may view/download ``export`` (already tenant-scoped).

    - SUPER_ADMIN: any export in the tenant
    - ADMIN: same branch as the export, or they requested it
      (tenant-wide / branch=None exports only if they requested them)
    - FACULTY / STUDENT / others: only exports they requested
    """
    if not user or not getattr(user, "is_authenticated", False):
        return False

    role = getattr(user, "role", None)
    if role == Role.SUPER_ADMIN:
        return True

    if export.requested_by_id and export.requested_by_id == user.pk:
        return True

    if role == Role.ADMIN:
        user_branch = getattr(user, "branch_id", None)
        if export.branch_id and user_branch and str(export.branch_id) == str(user_branch):
            return True
        return False

    return False


class CanRunReport(BasePermission):
    """Admin or super-admin may generate branch-scoped catalog exports."""

    message = "Admin or super-admin access required to run reports."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role in {Role.ADMIN, Role.SUPER_ADMIN}
        )


class CanDownloadReport(BasePermission):
    """Authenticated users may hit download/detail; object access is branch-gated."""

    message = "You do not have access to this report export."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, export):
        return user_can_access_export(request.user, export)
