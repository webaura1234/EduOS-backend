"""
DRF permission classes for EduOS.

Usage in views:
    permission_classes = [IsAuthenticated, IsAdmin]
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]
    permission_classes = [IsAuthenticated, MustChangePasswordPermission]
"""

from rest_framework.permissions import BasePermission

from apps.accounts.models.user import Role


# ─────────────────────────────────────────────────────────────────────────────
# Role-based permissions
# ─────────────────────────────────────────────────────────────────────────────

class IsPlatformOwner(BasePermission):
    """Allow access only to users with role=platform_owner (SaaS operator)."""
    message = "Platform owner access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role == Role.PLATFORM_OWNER)


class IsSuperAdmin(BasePermission):
    """Allow access only to users with role=super_admin."""
    message = "Super admin access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role == Role.SUPER_ADMIN)


class IsAdmin(BasePermission):
    """Allow access only to users with role=admin."""
    message = "Admin access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role == Role.ADMIN)


class IsAdminOrSuperAdmin(BasePermission):
    """Allow access to admin or super_admin roles."""
    message = "Admin or super-admin access required."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role in {Role.ADMIN, Role.SUPER_ADMIN}
        )


class IsFaculty(BasePermission):
    """Allow access only to users with role=faculty."""
    message = "Faculty access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role == Role.FACULTY)


class IsStudent(BasePermission):
    """Allow access only to users with role=student."""
    message = "Student access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role == Role.STUDENT)


class IsParent(BasePermission):
    """Allow access only to users with role=parent."""
    message = "Parent access required."

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated
                    and request.user.role == Role.PARENT)


class IsStaff(BasePermission):
    """Allow access to admin, super_admin, or faculty."""
    message = "Staff access required."

    def has_permission(self, request, view):
        return bool(
            request.user and request.user.is_authenticated
            and request.user.role in {Role.SUPER_ADMIN, Role.ADMIN, Role.FACULTY}
        )


# ─────────────────────────────────────────────────────────────────────────────
# Tenant-scoped object permission
# ─────────────────────────────────────────────────────────────────────────────

class IsSameTenant(BasePermission):
    """
    Object-level permission: the object must belong to request.user's tenant.

    Usage:
        permission_classes = [IsAuthenticated, IsSameTenant]
    The view's get_object() must return an object with a .tenant_id attribute.
    """
    message = "You do not have permission to access this resource."

    def has_object_permission(self, request, view, obj):
        return bool(
            request.user and request.user.is_authenticated
            and str(getattr(obj, "tenant_id", None)) == str(request.user.tenant_id)
        )


# ─────────────────────────────────────────────────────────────────────────────
# must_change_password enforcement (Option B — DRF permission class)
# ─────────────────────────────────────────────────────────────────────────────

class MustChangePasswordPermission(BasePermission):
    """
    Block all API calls when must_change_password=True.

    Applied globally in DEFAULT_PERMISSION_CLASSES so every authenticated
    endpoint is blocked until the user completes their forced password change.

    The ForceChangePasswordView explicitly excludes this by NOT including
    it in its permission_classes.
    """
    message = "You must change your password before accessing this resource."

    def has_permission(self, request, view):
        # Unauthenticated requests pass through (handled by IsAuthenticated)
        if not request.user or not request.user.is_authenticated:
            return True

        if request.user.must_change_password:
            return False

        return True
