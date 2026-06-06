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


def get_active_user_for_login(
    *,
    tenant_id: str,
    role: str,
    phone: str | None = None,
    custom_login_id: str | None = None,
) -> User | None:
    """
    Resolve a single active User for the authentication backend.

    Exactly one of `phone` / `custom_login_id` should be provided (the backend
    decides which, based on the role). Returns None if no unique match exists.
    """
    base_qs = User.objects.filter(tenant_id=tenant_id, role=role, is_active=True)
    try:
        if phone is not None:
            return base_qs.get(phone=phone)
        if custom_login_id is not None:
            return base_qs.get(custom_login_id=custom_login_id)
        return None
    except User.DoesNotExist:
        return None
    except User.MultipleObjectsReturned:
        logger.error(
            "Multiple users found for login: role=%s tenant=%s phone=%s custom_login_id=%s",
            role, tenant_id, phone, custom_login_id,
        )
        return None


# ─────────────────────────────────────────────────────────────────────────────
# User writes
# ─────────────────────────────────────────────────────────────────────────────

def create_invited_user(
    *,
    first_name: str,
    last_name: str,
    role: str,
    tenant_id,
    branch_id,
    phone: str | None,
    custom_login_id: str | None,
    email: str | None,
) -> User:
    """Create a new User with an unusable password (set later via invite accept)."""
    user = User(
        first_name=first_name,
        last_name=last_name,
        role=role,
        tenant_id=tenant_id,
        branch_id=branch_id,
        phone=phone,
        custom_login_id=custom_login_id,
        email=email,
        must_change_password=True,
    )
    user.set_unusable_password()
    user.save()
    return user


def set_user_password(user: User, raw_password: str) -> None:
    """Hash and persist a new password, clearing the must-change flag."""
    user.set_password(raw_password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password"])


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


def create_invite_token(user: User, sent_to_phone: str = "") -> InviteToken:
    """Create and return an InviteToken for a user."""
    return InviteToken.objects.create(user=user, sent_to_phone=sent_to_phone)


def mark_invite_used(invite: InviteToken) -> None:
    """Mark an InviteToken as used."""
    invite.is_used = True
    invite.save(update_fields=["is_used", "updated_at"])


# ─────────────────────────────────────────────────────────────────────────────
# OTP writes
# ─────────────────────────────────────────────────────────────────────────────

def create_otp_record(user: User, otp_hash: str, phone: str, expires_at) -> OTPRecord:
    """Create and return an OTPRecord."""
    return OTPRecord.objects.create(
        user=user,
        otp_hash=otp_hash,
        phone=phone,
        expires_at=expires_at,
    )


def increment_otp_attempt(otp_record: OTPRecord) -> None:
    """Increment the failed-attempt counter on an OTPRecord."""
    otp_record.attempt_count += 1
    otp_record.save(update_fields=["attempt_count", "updated_at"])


def mark_otp_used(otp_record: OTPRecord) -> None:
    """Mark an OTPRecord as used."""
    otp_record.is_used = True
    otp_record.save(update_fields=["is_used", "updated_at"])


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
