"""
Queries — user and token lookups.

Pure database access functions. No business logic here.
Callers (interactors) are responsible for interpreting the results.
"""

import logging
from datetime import timedelta

from django.utils import timezone

from apps.accounts.models.security import LoginAttempt
from apps.accounts.models.token import InviteToken, OTPRecord, RefreshToken
from apps.accounts.models.user import User

logger = logging.getLogger("apps.accounts.queries.user")


# ─────────────────────────────────────────────────────────────────────────────
# User lookups
# ─────────────────────────────────────────────────────────────────────────────

def get_user_by_id(user_id) -> User | None:
    """Return an active User by primary key (UUID), or None."""
    try:
        return User.objects.select_related("tenant", "branch").get(
            pk=user_id, is_active=True
        )
    except User.DoesNotExist:
        return None


def get_user_by_phone(phone: str, tenant_id: str) -> User | None:
    """Return an active User matching phone + tenant, or None."""
    try:
        return User.objects.select_related("tenant", "branch").get(
            phone=phone, tenant_id=tenant_id, is_active=True
        )
    except User.DoesNotExist:
        return None


def get_user_by_custom_login_id(custom_login_id: str, tenant_id: str) -> User | None:
    """Return an active User matching custom_login_id + tenant, or None."""
    try:
        return User.objects.select_related("tenant", "branch").get(
            custom_login_id=custom_login_id, tenant_id=tenant_id, is_active=True
        )
    except User.DoesNotExist:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Refresh token lookups
# ─────────────────────────────────────────────────────────────────────────────

def get_active_refresh_token(token_str: str) -> RefreshToken | None:
    """
    Return a RefreshToken that is not revoked and not expired, or None.
    """
    try:
        rt = RefreshToken.objects.select_related("user").get(token=token_str)
    except RefreshToken.DoesNotExist:
        return None

    if rt.is_revoked or rt.expires_at < timezone.now():
        return None

    return rt


# ─────────────────────────────────────────────────────────────────────────────
# OTP lookups
# ─────────────────────────────────────────────────────────────────────────────

def get_valid_otp(phone: str) -> OTPRecord | None:
    """
    Return the most recent unused, unexpired OTPRecord for this phone, or None.
    """
    return (
        OTPRecord.objects.filter(
            phone=phone,
            is_used=False,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )


def count_otps_in_window(phone: str, window_minutes: int) -> int:
    """Count OTPs sent to a phone within the last window_minutes."""
    since = timezone.now() - timedelta(minutes=window_minutes)
    return OTPRecord.objects.filter(phone=phone, created_at__gte=since).count()


# ─────────────────────────────────────────────────────────────────────────────
# Invite token lookups
# ─────────────────────────────────────────────────────────────────────────────

def get_valid_invite(token_uuid) -> InviteToken | None:
    """Return a valid (unused, unexpired) InviteToken, or None."""
    try:
        invite = InviteToken.objects.select_related("user").get(token=token_uuid)
    except InviteToken.DoesNotExist:
        return None

    if invite.is_used or invite.expires_at < timezone.now():
        return None

    return invite


# ─────────────────────────────────────────────────────────────────────────────
# Login attempt lookups
# ─────────────────────────────────────────────────────────────────────────────

def count_failed_attempts(identifier: str, tenant_id: str, window_minutes: int) -> int:
    """Count failed login attempts for identifier+tenant in the last window_minutes."""
    since = timezone.now() - timedelta(minutes=window_minutes)
    return LoginAttempt.objects.filter(
        identifier=identifier,
        tenant_id=tenant_id,
        was_successful=False,
        created_at__gte=since,
    ).count()


def record_login_attempt(
    identifier: str,
    tenant_id: str,
    ip_address: str,
    was_successful: bool,
    failure_reason: str = "",
) -> LoginAttempt:
    """Create and return a LoginAttempt record."""
    return LoginAttempt.objects.create(
        identifier=identifier,
        tenant_id=tenant_id,
        ip_address=ip_address,
        was_successful=was_successful,
        failure_reason=failure_reason,
    )
