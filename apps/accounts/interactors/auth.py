"""
Auth interactor — login, token refresh, logout.

All business logic for the core auth flow lives here.
Views call these functions; DB access goes through queries/.
Interactors return DTOs — never raw dicts.
"""

import logging

from django.contrib.auth import authenticate
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.accounts.dtos import LoginResponseDTO, TokenPairDTO

from apps.accounts.constants import (
    LOGIN_ATTEMPT_WINDOW_MINUTES,
    LOGIN_LOCKOUT_DURATION_MINUTES,
    MAX_LOGIN_ATTEMPTS,
)
from apps.accounts.queries.session import revoke_refresh_token
from apps.accounts.queries.user import (
    count_failed_attempts,
    get_active_refresh_token,
    record_login_attempt,
)
from apps.accounts.tokens import (
    decode_refresh_token,
    generate_access_token,
    generate_refresh_token,
)

logger = logging.getLogger("apps.accounts.interactors.auth")


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
    # 1. Check lockout
    failed_count = count_failed_attempts(
        identifier=identifier,
        tenant_id=tenant_id,
        window_minutes=LOGIN_ATTEMPT_WINDOW_MINUTES,
    )
    if failed_count >= MAX_LOGIN_ATTEMPTS:
        logger.warning(
            "Login locked out: identifier=%s tenant=%s failures=%d",
            identifier, tenant_id, failed_count,
        )
        record_login_attempt(
            identifier=identifier,
            tenant_id=tenant_id,
            ip_address=ip_address,
            was_successful=False,
            failure_reason="locked_out",
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
        # 3a. Record failure
        record_login_attempt(
            identifier=identifier,
            tenant_id=tenant_id,
            ip_address=ip_address,
            was_successful=False,
            failure_reason="wrong_password",
        )
        raise AuthenticationFailed("Invalid credentials.")

    # 3b. Record success
    record_login_attempt(
        identifier=identifier,
        tenant_id=tenant_id,
        ip_address=ip_address,
        was_successful=True,
    )

    # 4. Issue tokens
    access_token = generate_access_token(user)
    refresh_token_str, _ = generate_refresh_token(
        user=user,
        device_info=device_info,
        ip_address=ip_address,
    )

    logger.info("Login success: user=%s role=%s", user.id, user.role)

    return LoginResponseDTO(
        access=access_token,
        refresh=refresh_token_str,
        must_change_password=user.must_change_password,
        user_id=user.id,
        role=user.role,
    )


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
