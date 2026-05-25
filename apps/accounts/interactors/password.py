"""
Password interactor — forced change and OTP-based reset.

Business logic for:
  - force_change_password: first-login mandatory password change.
  - request_otp_reset: send OTP via SMS (or log in dev).
  - verify_otp_and_reset: verify OTP and set new password.
"""

import hashlib
import logging
import random
import string

from django.conf import settings
from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.accounts.constants import (
    OTP_EXPIRY_MINUTES,
    OTP_LENGTH,
    OTP_MAX_PER_WINDOW,
    OTP_WINDOW_MINUTES,
)
from apps.accounts.models.token import OTPRecord
from apps.accounts.queries.session import revoke_all_user_tokens
from apps.accounts.queries.user import (
    count_otps_in_window,
    get_user_by_phone,
    get_valid_otp,
)
from apps.accounts.validators import validate_password_strength
from datetime import timedelta

logger = logging.getLogger("apps.accounts.interactors.password")


# ─────────────────────────────────────────────────────────────────────────────
# Force change (first-login)
# ─────────────────────────────────────────────────────────────────────────────

def force_change_password(user, current_password: str, new_password: str) -> None:
    """
    Handle the mandatory first-login password change.

    Rules:
      - Current password must be correct.
      - New password must pass strength validation.
      - New password cannot be the same as current.
      - All existing refresh tokens are revoked (force re-login on all devices).
      - must_change_password set to False.

    Raises ValidationError or AuthenticationFailed on failure.
    """
    # Verify current password
    if not user.check_password(current_password):
        raise AuthenticationFailed("Current password is incorrect.")

    # Validate new password strength
    try:
        validate_password_strength(new_password)
    except ValidationError as exc:
        raise ValidationError(exc.messages)

    # Prevent reuse of the same password
    if user.check_password(new_password):
        raise ValidationError("New password must be different from the current password.")

    # Set new password and clear the flag
    user.set_password(new_password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password"])

    # Revoke all existing refresh tokens → forces re-login everywhere
    revoked_count = revoke_all_user_tokens(user)
    logger.info(
        "Password changed: user=%s revoked_tokens=%d", user.id, revoked_count
    )


# ─────────────────────────────────────────────────────────────────────────────
# OTP-based reset
# ─────────────────────────────────────────────────────────────────────────────

def _generate_otp() -> str:
    """Generate a random numeric OTP of OTP_LENGTH digits."""
    return "".join(random.choices(string.digits, k=OTP_LENGTH))


def _hash_otp(otp: str) -> str:
    """Return a SHA-256 hex digest of the OTP (stored in DB, never plain text)."""
    return hashlib.sha256(otp.encode()).hexdigest()


def _send_otp(phone: str, otp: str) -> None:
    """
    Send OTP via SMS in production; log to console in development.
    """
    if settings.DEBUG:
        logger.info("🔑 [DEV] OTP for %s: %s", phone, otp)
        return

    # Production: send via MSG91
    try:
        import requests
        response = requests.post(
            "https://api.msg91.com/api/v5/otp",
            json={
                "authkey": settings.MSG91_AUTH_KEY,
                "template_id": settings.MSG91_OTP_TEMPLATE_ID,  # set this in settings
                "mobile": phone,
                "OTP": otp,
            },
            timeout=10,
        )
        response.raise_for_status()
        logger.info("OTP sent to %s via MSG91", phone)
    except Exception as exc:
        logger.error("Failed to send OTP to %s: %s", phone, exc)
        raise ValidationError("Failed to send OTP. Please try again.")


def request_otp_reset(phone: str, tenant_id: str) -> None:
    """
    Send an OTP to the phone for password reset.

    Rate limit: max OTP_MAX_PER_WINDOW OTPs per phone per OTP_WINDOW_MINUTES.

    Raises PermissionDenied if rate limit exceeded.
    Does NOT raise if user not found (security: don't reveal if phone exists).
    """
    # Rate limit check (apply regardless of whether user exists)
    otp_count = count_otps_in_window(phone, OTP_WINDOW_MINUTES)
    if otp_count >= OTP_MAX_PER_WINDOW:
        raise PermissionDenied(
            f"Too many OTP requests. Please wait {OTP_WINDOW_MINUTES} minutes."
        )

    # Silently return if user not found (don't leak account existence)
    user = get_user_by_phone(phone, tenant_id)
    if user is None:
        logger.debug("OTP requested for unknown phone=%s tenant=%s", phone, tenant_id)
        return

    # Generate and store OTP hash
    otp = _generate_otp()
    otp_hash = _hash_otp(otp)
    expiry = timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)

    OTPRecord.objects.create(
        user=user,
        otp_hash=otp_hash,
        phone=phone,
        expires_at=expiry,
    )

    # Send OTP
    _send_otp(phone, otp)


def verify_otp_and_reset(phone: str, otp: str, new_password: str, tenant_id: str) -> None:
    """
    Verify the OTP and set the new password.

    Raises:
      AuthenticationFailed — OTP not found, expired, or wrong.
      ValidationError      — password doesn't meet strength requirements.
    """
    # Look up the most recent valid OTP for this phone
    otp_record = get_valid_otp(phone)
    if otp_record is None:
        raise AuthenticationFailed("OTP is invalid or has expired.")

    # Verify OTP hash
    if otp_record.otp_hash != _hash_otp(otp):
        # Increment attempt count
        otp_record.attempt_count += 1
        otp_record.save(update_fields=["attempt_count", "updated_at"])
        raise AuthenticationFailed("Incorrect OTP.")

    # Mark as used
    otp_record.is_used = True
    otp_record.save(update_fields=["is_used", "updated_at"])

    # Get the user
    user = otp_record.user

    # Validate + set new password
    try:
        validate_password_strength(new_password)
    except ValidationError as exc:
        raise ValidationError(exc.messages)

    user.set_password(new_password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password"])

    # Revoke all refresh tokens → force re-login
    revoke_all_user_tokens(user)

    logger.info("Password reset via OTP: user=%s", user.id)
