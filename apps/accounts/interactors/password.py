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

from django.core.exceptions import ValidationError
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.accounts.constants import (
    OTP_EXPIRY_MINUTES,
    OTP_LENGTH,
    OTP_MAX_PER_WINDOW,
    OTP_WINDOW_MINUTES,
)
from apps.accounts.models.user import Role
from apps.accounts.queries.session import revoke_all_user_tokens
from apps.accounts.queries.user import (
    count_otps_in_window,
    create_otp_record,
    get_reset_candidates,
    get_user_in_tenant,
    get_valid_otp,
    increment_otp_attempt,
    mark_otp_used,
    set_temp_password,
    set_user_password,
)
from apps.accounts.sms import send_sms
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
    set_user_password(user, new_password)

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
    """Send the OTP SMS via the circuit-breaker-protected dispatcher (EC-AUTH-16)."""
    send_sms(phone, f"Your EduOS password reset code is {otp}. It expires in 5 minutes.")


def list_reset_accounts(phone: str, tenant_id: str) -> list[dict]:
    """
    Return the accounts registered to a phone, for the reset account-picker
    (EC-AUTH-12 / EC-AUTH-20). Each entry: {user_id, role, name}.

    Empty list if none — the caller decides how to present it without leaking
    which specific phones exist.
    """
    return [
        {"user_id": str(u.id), "role": u.role, "name": u.full_name}
        for u in get_reset_candidates(phone, tenant_id)
    ]


def request_otp_reset(phone: str, tenant_id: str, account_id: str | None = None) -> None:
    """
    Send an OTP to the phone for password reset.

    Rate limit: max OTP_MAX_PER_WINDOW OTPs per phone per OTP_WINDOW_MINUTES.

    When the phone matches multiple accounts (EC-AUTH-12 / EC-AUTH-20), the caller
    must pass `account_id` (chosen from list_reset_accounts); otherwise a
    ValidationError signals that disambiguation is required.

    Raises:
      PermissionDenied   — rate limit exceeded.
      ValidationError    — multiple accounts and no account_id selected.
      ServiceUnavailableError — SMS gateway down (no OTP persisted).

    Does NOT raise if no account matches (security: don't reveal if phone exists).
    """
    # Rate limit check (apply regardless of whether an account exists)
    otp_count = count_otps_in_window(phone, OTP_WINDOW_MINUTES)
    if otp_count >= OTP_MAX_PER_WINDOW:
        raise PermissionDenied(
            f"Too many OTP requests. Please wait {OTP_WINDOW_MINUTES} minutes."
        )

    candidates = get_reset_candidates(phone, tenant_id)

    if not candidates:
        logger.debug("OTP requested for unknown phone=%s tenant=%s", phone, tenant_id)
        return  # don't leak account existence

    if account_id is not None:
        user = next((u for u in candidates if str(u.id) == str(account_id)), None)
        if user is None:
            # Selected account doesn't match this phone — treat as not found (no leak)
            logger.debug("Reset account_id %s not among candidates for phone=%s", account_id, phone)
            return
    elif len(candidates) > 1:
        raise ValidationError(
            "This phone is linked to multiple accounts. Please select which account to reset."
        )
    else:
        user = candidates[0]

    # Generate the OTP, send it FIRST, and only persist on a successful send so a
    # failed dispatch leaves no usable OTP behind (EC-AUTH-16).
    otp = _generate_otp()
    _send_otp(phone, otp)

    expiry = timezone.now() + timedelta(minutes=OTP_EXPIRY_MINUTES)
    create_otp_record(user=user, otp_hash=_hash_otp(otp), phone=phone, expires_at=expiry)


def _generate_temp_password() -> str:
    """Generate a temp password that always satisfies the strength rules."""
    body = "".join(random.choices(string.ascii_lowercase, k=6))
    digits = "".join(random.choices(string.digits, k=3))
    return f"Tmp{body}{digits}!"  # upper (T) + lower + digit + special


def admin_reset_password(admin, target_user_id: str, temp_password: str | None = None) -> str:
    """
    Admin manually resets a user's password (EC-AUTH-21).

    Sets a temporary password and forces a change on the target's next login.
    Revokes the target's existing sessions. Returns the temp password so the
    admin can relay it to the user.

    Raises:
      PermissionDenied  — caller is not an admin/super_admin.
      ValidationError   — target user not found in the admin's tenant.
    """
    if admin.role not in {Role.ADMIN, Role.SUPER_ADMIN}:
        raise PermissionDenied("Only admins can reset user passwords.")

    target = get_user_in_tenant(target_user_id, admin.tenant_id)
    if target is None:
        raise ValidationError("User not found in your institution.")

    temp = temp_password or _generate_temp_password()
    validate_password_strength(temp)

    set_temp_password(target, temp)
    revoke_all_user_tokens(target)

    logger.info("Admin %s reset password for user=%s", admin.id, target.id)
    return temp


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
        increment_otp_attempt(otp_record)
        raise AuthenticationFailed("Incorrect OTP.")

    # Mark as used
    mark_otp_used(otp_record)

    # Get the user
    user = otp_record.user

    # Validate + set new password
    try:
        validate_password_strength(new_password)
    except ValidationError as exc:
        raise ValidationError(exc.messages)

    set_user_password(user, new_password)

    # Revoke all refresh tokens → force re-login
    revoke_all_user_tokens(user)

    logger.info("Password reset via OTP: user=%s", user.id)
