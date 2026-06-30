"""
JWT token engine for EduOS.

Provides low-level encode / decode helpers for access and refresh tokens.
Uses PyJWT directly (no third-party DRF wrapper) for full control.

Access token  → short-lived (15 min), stateless, carries user claims.
Refresh token → long-lived (7 days), stored in DB, used to issue new access tokens.
"""

import uuid
from datetime import timezone as dt_timezone

import jwt
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.models.token import RefreshToken
from apps.accounts.queries.session import create_refresh_token_record


# ─────────────────────────────────────────────────────────────────────────────
# Access Token Revocation (JTI blocklist — backed by Redis)
# ─────────────────────────────────────────────────────────────────────────────

_REVOKED_JTI_PREFIX = "revoked_jti:"


def revoke_access_token_jti(jti: str, ttl_seconds: int) -> None:
    """Blocklist an access token by JTI. Expires automatically after ttl_seconds."""
    if ttl_seconds > 0:
        cache.set(f"{_REVOKED_JTI_PREFIX}{jti}", "1", timeout=ttl_seconds)


def is_access_token_revoked(jti: str) -> bool:
    """Return True if this JTI has been explicitly revoked."""
    return bool(cache.get(f"{_REVOKED_JTI_PREFIX}{jti}"))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _jwt_settings():
    return settings.JWT


def _signing_key():
    return _jwt_settings()["SIGNING_KEY"]


def _algorithm():
    return _jwt_settings()["ALGORITHM"]


# ─────────────────────────────────────────────────────────────────────────────
# Access Token
# ─────────────────────────────────────────────────────────────────────────────

def generate_access_token(user) -> str:
    """
    Encode and return a signed JWT access token for the given user.

    Payload claims:
      sub         — user UUID (str)
      role        — user role string
      tenant_id   — tenant UUID (str) or None
      branch_id   — branch UUID (str) or None
      jti         — unique token ID (UUID4)
      iat         — issued-at timestamp
      exp         — expiry timestamp (now + ACCESS_TOKEN_LIFETIME)
    """
    cfg = _jwt_settings()
    now = timezone.now()
    exp = now + cfg["ACCESS_TOKEN_LIFETIME"]

    payload = {
        "sub": str(user.id),
        "role": user.role,
        "tenant_id": str(user.tenant_id) if user.tenant_id else None,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "token_type": "access",
    }

    return jwt.encode(payload, _signing_key(), algorithm=_algorithm())


def decode_access_token(token: str) -> dict:
    """
    Decode and verify an access token.

    Raises AuthenticationFailed on any error (expired, bad signature, malformed).
    Returns the decoded payload dict on success.
    """
    try:
        payload = jwt.decode(
            token,
            _signing_key(),
            algorithms=[_algorithm()],
            options={"require": ["sub", "exp", "jti", "token_type"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailed("Access token has expired.")
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailed(f"Invalid access token: {exc}")

    if payload.get("token_type") != "access":
        raise AuthenticationFailed("Token type must be 'access'.")

    return payload


# ─────────────────────────────────────────────────────────────────────────────
# Refresh Token
# ─────────────────────────────────────────────────────────────────────────────

def generate_refresh_token(user, device_info: str = "", ip_address: str = None) -> tuple[str, RefreshToken]:
    """
    Encode a refresh token and persist it to the DB.

    Returns (token_string, RefreshToken_instance).
    The DB record allows revocation and replay prevention.
    """
    cfg = _jwt_settings()
    now = timezone.now()
    exp = now + cfg["REFRESH_TOKEN_LIFETIME"]
    jti = str(uuid.uuid4())

    payload = {
        "sub": str(user.id),
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "token_type": "refresh",
    }

    token_str = jwt.encode(payload, _signing_key(), algorithm=_algorithm())

    # Persist to DB for revocation support (DB access lives in queries/)
    db_record = create_refresh_token_record(
        user=user,
        token=token_str,
        expires_at=exp,
        device_info=device_info,
        ip_address=ip_address,
    )

    return token_str, db_record


def decode_refresh_token(token: str) -> dict:
    """
    Decode and verify a refresh token (signature + expiry only).

    Does NOT check DB revocation — callers must do that themselves.
    Raises AuthenticationFailed on any error.
    """
    try:
        payload = jwt.decode(
            token,
            _signing_key(),
            algorithms=[_algorithm()],
            options={"require": ["sub", "exp", "jti", "token_type"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailed("Refresh token has expired.")
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailed(f"Invalid refresh token: {exc}")

    if payload.get("token_type") != "refresh":
        raise AuthenticationFailed("Token type must be 'refresh'.")

    return payload


# ─────────────────────────────────────────────────────────────────────────────
# MFA Session Token  (short-lived, 10 min, used between password-OK and OTP-OK)
# ─────────────────────────────────────────────────────────────────────────────

_MFA_SESSION_LIFETIME_SECONDS = 10 * 60  # 10 minutes


def generate_mfa_session_token(user) -> str:
    """
    Issue a short-lived MFA session token after password verification passes.

    This is NOT an access token — it cannot authenticate any API call.
    It only proves that the password step succeeded for this user.
    """
    now = timezone.now()
    exp = now.timestamp() + _MFA_SESSION_LIFETIME_SECONDS
    payload = {
        "sub": str(user.id),
        "token_type": "mfa_session",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(exp),
    }
    return jwt.encode(payload, _signing_key(), algorithm=_algorithm())


def decode_mfa_session_token(token: str) -> dict:
    """
    Decode and verify an MFA session token.
    Raises AuthenticationFailed on any error.
    """
    try:
        payload = jwt.decode(
            token,
            _signing_key(),
            algorithms=[_algorithm()],
            options={"require": ["sub", "exp", "jti", "token_type"]},
        )
    except jwt.ExpiredSignatureError:
        raise AuthenticationFailed("MFA session has expired. Please log in again.")
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailed(f"Invalid MFA session token: {exc}")

    if payload.get("token_type") != "mfa_session":
        raise AuthenticationFailed("Invalid token type.")

    return payload
