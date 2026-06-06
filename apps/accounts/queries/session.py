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
) -> RefreshToken:
    """Persist a refresh token record (enables revocation + replay prevention)."""
    return RefreshToken.objects.create(
        user=user,
        token=token,
        expires_at=expires_at,
        device_info=device_info,
        ip_address=ip_address,
    )


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


def delete_expired_tokens() -> int:
    """
    Hard-delete refresh tokens that have expired.

    Called by a periodic Celery task to keep the table clean.
    Returns the number of tokens deleted.
    """
    count, _ = RefreshToken.objects.filter(expires_at__lt=timezone.now()).delete()
    return count
