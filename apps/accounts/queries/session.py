"""
Queries — refresh token session management.

Handles creating, rotating, and revoking refresh tokens in the DB.
"""

import logging

from django.utils import timezone

from apps.accounts.models.token import RefreshToken
from apps.accounts.models.user import User

logger = logging.getLogger("apps.accounts.queries.session")


def create_refresh_token_record(
    *,
    user: User,
    token: str,
    expires_at,
    device_info: str = "",
    ip_address: str = None,
    family_id=None,
    generation: int = 1,
) -> RefreshToken:
    """Persist a refresh token record (enables revocation + replay prevention)."""
    import uuid as _uuid
    return RefreshToken.objects.create(
        user=user,
        token=token,
        expires_at=expires_at,
        device_info=device_info,
        ip_address=ip_address,
        family_id=family_id or _uuid.uuid4(),
        generation=generation,
    )


def get_refresh_token_any_state(token_str: str) -> RefreshToken | None:
    """
    Return a RefreshToken regardless of revocation status.

    Used for replay detection: if the token exists but is already revoked,
    that signals a stolen token was reused.
    """
    try:
        return RefreshToken.objects.select_related("user").get(token=token_str)
    except RefreshToken.DoesNotExist:
        return None


def revoke_token_family(family_id) -> int:
    """
    Revoke every token in a rotation family.

    Called when a revoked token is presented again — signals theft.
    Returns the number of tokens revoked.
    """
    count = RefreshToken.objects.filter(family_id=family_id, is_revoked=False).update(is_revoked=True)
    logger.warning("Token family %s fully revoked (%d token(s)) — possible replay attack", family_id, count)
    return count


def revoke_refresh_token(token_str: str) -> bool:
    """
    Mark a refresh token as revoked.

    Returns True if the token was found and revoked, False if not found.
    """
    updated = RefreshToken.objects.filter(token=token_str).update(is_revoked=True)
    return updated > 0


def revoke_all_user_tokens(user: User) -> int:
    """
    Revoke ALL active refresh tokens for a user.

    Used after password change to force re-login on all devices.
    Returns the number of tokens revoked.
    """
    return RefreshToken.objects.filter(
        user=user,
        is_revoked=False,
    ).update(is_revoked=True)


def count_active_sessions_for_tenant(tenant_id) -> int:
    """Count non-revoked, non-expired refresh tokens across all users of a tenant."""
    return RefreshToken.objects.filter(
        user__tenant_id=tenant_id,
        is_revoked=False,
        expires_at__gt=timezone.now(),
    ).count()


def revoke_tokens_for_tenant(tenant_id) -> int:
    """
    Revoke every active refresh token for a tenant's users (session-kill on tenant
    deactivation, EC-TEN-04). Returns the number of sessions terminated.
    """
    return RefreshToken.objects.filter(
        user__tenant_id=tenant_id,
        is_revoked=False,
    ).update(is_revoked=True)


def delete_expired_tokens() -> int:
    """
    Hard-delete refresh tokens that have expired.

    Called by a periodic Celery task to keep the table clean.
    Returns the number of tokens deleted.
    """
    count, _ = RefreshToken.objects.filter(expires_at__lt=timezone.now()).delete()
    return count
