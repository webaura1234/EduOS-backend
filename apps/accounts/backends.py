"""
EduOS authentication backend.

EduOSAuthBackend handles role-based login identifier resolution:
  - super_admin, admin, parent  → login via phone number
  - faculty                     → login via custom_login_id (Employee ID)
  - student                     → login via custom_login_id (Roll Number)
"""

import logging
import re

from django.contrib.auth.backends import ModelBackend

from apps.accounts.models.user import Role, User
from apps.accounts.queries.user import get_active_user_for_login

logger = logging.getLogger("apps.accounts.backends")


def _normalize_phone(identifier: str) -> str:
    """Normalize Indian mobile numbers to E.164 (+91...) for lookup."""
    cleaned = re.sub(r"[\s\-]", "", identifier)
    if cleaned.startswith("+91"):
        return cleaned
    if cleaned.startswith("0") and len(cleaned) == 11:
        return f"+91{cleaned[1:]}"
    if re.fullmatch(r"[6-9]\d{9}", cleaned):
        return f"+91{cleaned}"
    return identifier


# Roles that use phone number as login identifier
PHONE_LOGIN_ROLES = {Role.SUPER_ADMIN, Role.ADMIN, Role.PARENT}

# Roles that use custom_login_id as login identifier
CUSTOM_ID_LOGIN_ROLES = {Role.FACULTY, Role.STUDENT}


class EduOSAuthBackend(ModelBackend):
    """
    Custom authentication backend for EduOS.

    authenticate() resolves the correct User based on role + identifier + tenant.
    Inherits has_perm / has_module_perms from ModelBackend.
    """

    def authenticate(
        self,
        request,
        username=None,
        password=None,
        identifier=None,
        role=None,
        tenant_id=None,
        **kwargs,
    ):
        """
        Look up a User matching the identifier for the given role and tenant,
        then verify the password.

        Used by the REST API (identifier + role + tenant_id). Django admin uses
        ModelBackend with USERNAME_FIELD=email instead.

        Parameters
        ----------
        identifier : str
            Phone number (for admin/parent) or custom_login_id (for faculty/student).
        password : str
            Plain-text password to verify.
        role : str
            One of Role.choices values.
        tenant_id : str
            UUID of the Tenant this user belongs to.

        Returns
        -------
        User | None
            Authenticated User or None if credentials are wrong.
        """
        if not all([identifier, password, role, tenant_id]):
            return None

        user = self._fetch_user(identifier, role, tenant_id)

        if user is None:
            logger.debug(
                "Auth failed: no user found for identifier=%s role=%s tenant=%s",
                identifier, role, tenant_id,
            )
            return None

        if not user.check_password(password):
            logger.debug(
                "Auth failed: wrong password for user=%s", user.id
            )
            return None

        return user

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_user(identifier: str, role: str, tenant_id: str) -> User | None:
        """Return the User matching identifier+role+tenant, or None.

        Resolves which identifier field to use based on role; all DB access is
        delegated to the queries layer.
        """
        if role in PHONE_LOGIN_ROLES:
            return get_active_user_for_login(
                tenant_id=tenant_id, role=role, phone=_normalize_phone(identifier)
            )
        elif role in CUSTOM_ID_LOGIN_ROLES:
            return get_active_user_for_login(
                tenant_id=tenant_id, role=role, custom_login_id=identifier
            )
        else:
            logger.warning("Unknown role '%s' passed to EduOSAuthBackend", role)
            return None
