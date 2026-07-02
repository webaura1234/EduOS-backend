"""
Identity-change interactors — change phone number and change email address.

Flow for phone:
  1. initiate_phone_change(user, new_phone) → sends OTP SMS to new_phone
  2. confirm_phone_change(user, otp)        → verifies OTP, updates user.phone

Flow for email:
  1. initiate_email_change(user, new_email) → sends OTP email to new_email
  2. confirm_email_change(user, otp)        → verifies OTP, updates user.email

Callers should ensure step-up auth has been completed before calling initiate.
"""

import hashlib
import logging
import random
import string
from datetime import timedelta

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, ValidationError

from apps.accounts.models.security import PendingIdentityChange
from apps.accounts.phone import normalize_phone

logger = logging.getLogger("apps.accounts.interactors.identity")

_OTP_EXPIRY_MINUTES = 10
_MAX_ATTEMPTS = PendingIdentityChange.MAX_ATTEMPTS


def _gen_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _hash_otp(otp: str) -> str:
    return hashlib.sha256(otp.encode()).hexdigest()


def _cancel_existing(user, change_type: str) -> None:
    PendingIdentityChange.objects.filter(
        user=user,
        change_type=change_type,
        is_verified=False,
    ).update(is_verified=True)


# ─── Phone ────────────────────────────────────────────────────────────────────

def initiate_phone_change(user, new_phone: str) -> None:
    """Send an OTP to new_phone to verify ownership before updating the account."""
    from apps.accounts.models import User
    from apps.accounts.sms import send_sms

    new_phone = normalize_phone(new_phone.strip())

    if User.objects.filter(phone=new_phone, tenant=user.tenant).exclude(pk=user.pk).exists():
        raise ValidationError("This phone number is already registered to another account.")

    if user.phone == new_phone:
        raise ValidationError("This is already your current phone number.")

    otp = _gen_otp()
    _cancel_existing(user, "phone")

    send_sms(
        new_phone,
        f"Your EduOS phone change verification code is {otp}. "
        f"Valid for {_OTP_EXPIRY_MINUTES} minutes. Do not share this code.",
    )

    PendingIdentityChange.objects.create(
        user=user,
        change_type="phone",
        new_value=new_phone,
        otp_hash=_hash_otp(otp),
        expires_at=timezone.now() + timedelta(minutes=_OTP_EXPIRY_MINUTES),
    )

    if settings.DEBUG:
        logger.info(
            "[DEV OTP] phone change user=%s new=%s otp=%s", user.id, new_phone, otp
        )


def confirm_phone_change(user, otp: str) -> None:
    """Verify OTP and update user.phone."""
    pending = (
        PendingIdentityChange.objects.filter(
            user=user,
            change_type="phone",
            is_verified=False,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )

    if pending is None:
        raise AuthenticationFailed("No pending phone change found or it has expired. Please request a new code.")

    if pending.attempt_count >= _MAX_ATTEMPTS:
        raise AuthenticationFailed("Too many incorrect attempts. Please request a new OTP.")

    if pending.otp_hash != _hash_otp(otp):
        pending.attempt_count += 1
        pending.save(update_fields=["attempt_count", "updated_at"])
        remaining = _MAX_ATTEMPTS - pending.attempt_count
        raise AuthenticationFailed(
            f"Incorrect OTP. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
        )

    pending.is_verified = True
    pending.save(update_fields=["is_verified", "updated_at"])

    user.phone = pending.new_value
    user.save(update_fields=["phone"])

    logger.info("Phone changed for user=%s to %s", user.id, pending.new_value[-4:])


# ─── Email ────────────────────────────────────────────────────────────────────

def initiate_email_change(user, new_email: str) -> None:
    """Send an OTP to new_email to verify ownership before updating the account."""
    from apps.accounts.models import User
    from apps.accounts.email import send_email

    new_email = new_email.strip().lower()

    if User.objects.filter(email=new_email, tenant=user.tenant).exclude(pk=user.pk).exists():
        raise ValidationError("This email address is already registered to another account.")

    if user.email and user.email.lower() == new_email:
        raise ValidationError("This is already your current email address.")

    otp = _gen_otp()
    _cancel_existing(user, "email")

    html_body = (
        f"<p>Hello {user.full_name},</p>"
        f"<p>Your EduOS email change verification code is:</p>"
        f"<h2 style='letter-spacing:4px;font-family:monospace'>{otp}</h2>"
        f"<p>Valid for <strong>{_OTP_EXPIRY_MINUTES} minutes</strong>.</p>"
        f"<p>If you did not request this change, contact your administrator immediately.</p>"
        f"<p>— The EduOS Team</p>"
    )
    text_body = (
        f"Hello {user.full_name},\n\n"
        f"Your EduOS email change verification code is: {otp}\n\n"
        f"Valid for {_OTP_EXPIRY_MINUTES} minutes.\n\n"
        f"If you did not request this, contact your administrator immediately.\n\n"
        f"— The EduOS Team"
    )
    send_email(new_email, user.full_name, "Verify your new email address — EduOS", html_body, text_body)

    PendingIdentityChange.objects.create(
        user=user,
        change_type="email",
        new_value=new_email,
        otp_hash=_hash_otp(otp),
        expires_at=timezone.now() + timedelta(minutes=_OTP_EXPIRY_MINUTES),
    )

    if settings.DEBUG:
        logger.info(
            "[DEV OTP] email change user=%s new=%s otp=%s", user.id, new_email, otp
        )


def confirm_email_change(user, otp: str) -> None:
    """Verify OTP and update user.email."""
    pending = (
        PendingIdentityChange.objects.filter(
            user=user,
            change_type="email",
            is_verified=False,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )

    if pending is None:
        raise AuthenticationFailed("No pending email change found or it has expired. Please request a new code.")

    if pending.attempt_count >= _MAX_ATTEMPTS:
        raise AuthenticationFailed("Too many incorrect attempts. Please request a new OTP.")

    if pending.otp_hash != _hash_otp(otp):
        pending.attempt_count += 1
        pending.save(update_fields=["attempt_count", "updated_at"])
        remaining = _MAX_ATTEMPTS - pending.attempt_count
        raise AuthenticationFailed(
            f"Incorrect OTP. {remaining} attempt{'s' if remaining != 1 else ''} remaining."
        )

    pending.is_verified = True
    pending.save(update_fields=["is_verified", "updated_at"])

    user.email = pending.new_value
    user.save(update_fields=["email"])

    logger.info("Email changed for user=%s", user.id)
