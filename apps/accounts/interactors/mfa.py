"""
MFA interactor — email OTP challenge and verification.

Flow:
  1. After password verified → issue_mfa_challenge(user) sends OTP to email,
     stores hash in MFAToken, returns MFARequiredDTO with short-lived session token.
  2. User submits OTP → verify_mfa_otp(session_token, otp) decodes session token,
     verifies OTP hash, marks token used, issues real access + refresh pair.
"""

import hashlib
import logging
import secrets

from rest_framework.exceptions import AuthenticationFailed

from apps.accounts.dtos import MFARequiredDTO
from apps.accounts.models.token import MFAToken
from apps.accounts.models.user import Role
from apps.accounts.queries.user import get_user_for_token
from apps.accounts.tokens import (
    decode_mfa_session_token,
    generate_mfa_session_token,
)

logger = logging.getLogger("apps.accounts.interactors.mfa")

MFA_REQUIRED_ROLES = {Role.ADMIN, Role.SUPER_ADMIN, Role.PLATFORM_OWNER}


def _generate_otp() -> str:
    """Cryptographically random 6-digit OTP."""
    return str(secrets.randbelow(900000) + 100000)


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.strip().encode()).hexdigest()


def _mask_email(email: str) -> str:
    try:
        local, domain = email.split("@", 1)
        masked = local[0] + "***" if len(local) > 1 else "*"
        return f"{masked}@{domain}"
    except ValueError:
        return "***@***"


def issue_mfa_challenge(user) -> "MFARequiredDTO | None":
    """
    Send OTP to user's email and return an MFA challenge DTO.

    Returns None if the user has no email — caller should fall back to issuing tokens
    directly (graceful degradation until email becomes mandatory for admin roles).
    """
    if not user.email:
        logger.warning(
            "MFA required but user=%s role=%s has no email — skipping MFA",
            user.id, user.role,
        )
        return None

    otp = _generate_otp()
    otp_hash = _hash_otp(otp)

    # Invalidate any pending MFA tokens before issuing a new one.
    MFAToken.objects.filter(user=user, is_used=False).update(is_used=True)

    MFAToken.objects.create(
        user=user,
        otp_hash=otp_hash,
        email_sent_to=user.email,
    )

    from apps.accounts.email import send_mfa_otp_email
    send_mfa_otp_email(
        to_email=user.email,
        to_name=user.first_name or user.full_name or "User",
        otp=otp,
    )

    mfa_session_token = generate_mfa_session_token(user)
    email_hint = _mask_email(user.email)
    logger.info("MFA challenge issued: user=%s email=%s", user.id, email_hint)

    return MFARequiredDTO(mfa_session_token=mfa_session_token, email_hint=email_hint)


def verify_mfa_otp(
    mfa_session_token: str,
    otp: str,
    device_info: str = "",
    ip_address: str = None,
):
    """
    Verify the OTP submitted for an MFA challenge.

    Returns LoginResponseDTO on success.
    Raises AuthenticationFailed on any failure.
    """
    from apps.accounts.interactors.auth import _issue_login_tokens

    payload = decode_mfa_session_token(mfa_session_token)
    user_id = payload.get("sub")

    user = get_user_for_token(user_id)
    if user is None or not user.is_active:
        raise AuthenticationFailed("Invalid MFA session. Please log in again.")

    mfa_token = (
        MFAToken.objects
        .filter(user=user, is_used=False)
        .order_by("-created_at")
        .first()
    )

    if mfa_token is None:
        raise AuthenticationFailed("No pending MFA challenge. Please log in again.")

    if mfa_token.is_expired:
        raise AuthenticationFailed("Verification code has expired. Please log in again.")

    if mfa_token.attempt_count >= MFAToken.MAX_ATTEMPTS:
        raise AuthenticationFailed("Too many failed attempts. Please log in again.")

    submitted_hash = _hash_otp(otp)
    if submitted_hash != mfa_token.otp_hash:
        mfa_token.attempt_count += 1
        mfa_token.save(update_fields=["attempt_count"])
        remaining = MFAToken.MAX_ATTEMPTS - mfa_token.attempt_count
        if remaining <= 0:
            logger.warning("MFA max attempts exceeded: user=%s", user.id)
            raise AuthenticationFailed("Too many failed attempts. Please log in again.")
        raise AuthenticationFailed(
            f"Invalid verification code. {remaining} attempt(s) remaining."
        )

    mfa_token.is_used = True
    mfa_token.save(update_fields=["is_used"])

    logger.info("MFA verified: user=%s role=%s", user.id, user.role)
    return _issue_login_tokens(user, device_info, ip_address)
