"""
Auth interactor — login, token refresh, logout.

All business logic for the core auth flow lives here.
Views call these functions; DB access goes through queries/.
Interactors return DTOs — never raw dicts.
"""

import logging

from django.contrib.auth import authenticate
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.accounts.backends import _normalize_phone
from apps.accounts.dtos import LoginResolutionDTO, LoginResponseDTO, TokenPairDTO

from apps.accounts.constants import (
    LOGIN_ATTEMPT_WINDOW_MINUTES,
    LOGIN_LOCKOUT_DURATION_MINUTES,
    MAX_LOGIN_ATTEMPTS,
)
from apps.accounts.models.user import PHONE_LOGIN_ROLES, Role
from apps.accounts.queries.session import revoke_refresh_token
from apps.accounts.queries.user import (
    count_failed_attempts,
    count_failed_attempts_for_user,
    get_active_refresh_token,
    get_active_user_for_login,
    get_phone_login_candidates,
    record_login_attempt,
)
from apps.accounts.tokens import (
    decode_refresh_token,
    generate_access_token,
    generate_refresh_token,
)

logger = logging.getLogger("apps.accounts.interactors.auth")


def _resolve_candidate_user(identifier: str, role: str, tenant_id: str):
    """Resolve the user an identifier+role points to (no password check) for lockout scoping."""
    if role in PHONE_LOGIN_ROLES:
        return get_active_user_for_login(
            tenant_id=tenant_id, role=role, phone=_normalize_phone(identifier)
        )
    return get_active_user_for_login(
        tenant_id=tenant_id, role=role, custom_login_id=identifier
    )


def _check_parent_portal(user) -> None:
    """EC-AUTH-26: block parent login when the institution has the parent portal disabled."""
    if user.role == Role.PARENT and user.tenant and not user.tenant.parent_access_enabled:
        raise PermissionDenied("The parent portal is not available for this institution.")


def _issue_login_tokens(user, device_info: str, ip_address: str) -> LoginResponseDTO:
    """Issue an access + refresh pair and build the login DTO."""
    access_token = generate_access_token(user)
    refresh_token_str, _ = generate_refresh_token(
        user=user, device_info=device_info, ip_address=ip_address
    )
    return LoginResponseDTO(
        access=access_token,
        refresh=refresh_token_str,
        must_change_password=user.must_change_password,
        user_id=user.id,
        role=user.role,
    )


def login(
    identifier: str,
    password: str,
    role: str,
    tenant_id: str,
    device_info: str = "",
    ip_address: str = None,
) -> LoginResponseDTO:
    """
    Authenticate a user and return a token pair.

    Flow:
      1. Check brute-force lockout (5 failures in 30 min → locked 15 min).
      2. Delegate credential verification to EduOSAuthBackend.
      3. Record the login attempt (success or failure).
      4. Issue access + refresh tokens.
      5. Return token pair with user metadata.

    Raises
    ------
    PermissionDenied   — when the identifier is currently locked out.
    AuthenticationFailed — when credentials are invalid.
    """
    # 0. Resolve which user this identifier points to (for user-scoped lockout, EC-AUTH-25)
    candidate = _resolve_candidate_user(identifier, role, tenant_id)

    # 1. Check lockout — scoped to the resolved user when known, else to the raw identifier
    if candidate is not None:
        failed_count = count_failed_attempts_for_user(
            candidate.id, window_minutes=LOGIN_ATTEMPT_WINDOW_MINUTES
        )
    else:
        failed_count = count_failed_attempts(
            identifier=identifier,
            tenant_id=tenant_id,
            window_minutes=LOGIN_ATTEMPT_WINDOW_MINUTES,
        )

    if failed_count >= MAX_LOGIN_ATTEMPTS:
        logger.warning(
            "Login locked out: identifier=%s tenant=%s user=%s failures=%d",
            identifier, tenant_id, getattr(candidate, "id", None), failed_count,
        )
        record_login_attempt(
            identifier=identifier,
            tenant_id=tenant_id,
            ip_address=ip_address,
            was_successful=False,
            failure_reason="locked_out",
            user=candidate,
        )
        raise PermissionDenied(
            f"Too many failed attempts. Please try again in "
            f"{LOGIN_LOCKOUT_DURATION_MINUTES} minutes."
        )

    # 2. Verify credentials via auth backend
    user = authenticate(
        request=None,
        identifier=identifier,
        password=password,
        role=role,
        tenant_id=tenant_id,
    )

    if user is None:
        # 3a. Record failure (tied to the resolved user when known)
        record_login_attempt(
            identifier=identifier,
            tenant_id=tenant_id,
            ip_address=ip_address,
            was_successful=False,
            failure_reason="wrong_password",
            user=candidate,
        )
        raise AuthenticationFailed("Invalid credentials.")

    # 3b. Enforce the parent-portal gate before issuing any session (EC-AUTH-26)
    _check_parent_portal(user)

    # 3c. Record success
    record_login_attempt(
        identifier=identifier,
        tenant_id=tenant_id,
        ip_address=ip_address,
        was_successful=True,
        user=user,
    )

    # 4. Issue tokens
    logger.info("Login success: user=%s role=%s", user.id, user.role)
    return _issue_login_tokens(user, device_info, ip_address)


def disambiguate_login(
    identifier: str,
    password: str,
    tenant_id: str,
    device_info: str = "",
    ip_address: str = None,
) -> LoginResolutionDTO:
    """
    Resolve a login when the role isn't specified up front (EC-AUTH-11).

    Flow:
      1. If the identifier is a phone shared by multiple phone-login roles
         (admin + parent), verify the password against each. If more than one
         account matches, return the candidate list for a role picker — password
         is verified BEFORE the picker is shown, and no token is issued yet.
      2. If exactly one account matches (phone or custom_id), log the user in.
      3. Otherwise, fall back to a custom_id lookup (faculty/student).
    """
    normalized_phone = _normalize_phone(identifier)
    phone_candidates = get_phone_login_candidates(normalized_phone, tenant_id)
    matched = [u for u in phone_candidates if u.check_password(password)]

    if len(matched) > 1:
        # Password verified; ask the client to pick a role (EC-AUTH-11).
        return LoginResolutionDTO(
            requires_selection=True,
            accounts=[
                {"user_id": str(u.id), "role": u.role, "name": u.full_name}
                for u in matched
            ],
        )

    if len(matched) == 1:
        user = matched[0]
        _check_parent_portal(user)
        record_login_attempt(
            identifier=identifier, tenant_id=tenant_id, ip_address=ip_address,
            was_successful=True, user=user,
        )
        return LoginResolutionDTO(login=_issue_login_tokens(user, device_info, ip_address))

    # No phone match — try custom_id login (faculty, then student)
    for role in (Role.FACULTY, Role.STUDENT):
        user = get_active_user_for_login(
            tenant_id=tenant_id, role=role, custom_login_id=identifier
        )
        if user and user.check_password(password):
            record_login_attempt(
                identifier=identifier, tenant_id=tenant_id, ip_address=ip_address,
                was_successful=True, user=user,
            )
            return LoginResolutionDTO(login=_issue_login_tokens(user, device_info, ip_address))

    record_login_attempt(
        identifier=identifier, tenant_id=tenant_id, ip_address=ip_address,
        was_successful=False, failure_reason="wrong_password",
    )
    raise AuthenticationFailed("Invalid credentials.")


def refresh_tokens(refresh_token_str: str, device_info: str = "", ip_address: str = None) -> TokenPairDTO:
    """
    Rotate a refresh token and return a new token pair.

    Token rotation: the old refresh token is revoked and a new one is issued.
    This prevents refresh token replay attacks.

    Raises AuthenticationFailed if the token is invalid, expired, or revoked.
    """
    # Verify JWT signature and expiry
    payload = decode_refresh_token(refresh_token_str)

    # Check DB — token must not be revoked
    db_token = get_active_refresh_token(refresh_token_str)
    if db_token is None:
        raise AuthenticationFailed("Refresh token is invalid, expired, or has been revoked.")

    user = db_token.user
    if not user.is_active:
        raise AuthenticationFailed("User account is inactive.")

    # Revoke old token (rotation)
    revoke_refresh_token(refresh_token_str)

    # Issue new pair
    new_access = generate_access_token(user)
    new_refresh_str, _ = generate_refresh_token(
        user=user,
        device_info=device_info,
        ip_address=ip_address,
    )

    logger.info("Token rotated: user=%s", user.id)

    return TokenPairDTO(
        access=new_access,
        refresh=new_refresh_str,
    )


def logout(refresh_token_str: str) -> None:
    """
    Revoke the given refresh token, logging the user out on this device.

    Does not raise if the token is already revoked (idempotent).
    """
    revoked = revoke_refresh_token(refresh_token_str)
    if not revoked:
        logger.debug("Logout: token not found or already revoked.")
