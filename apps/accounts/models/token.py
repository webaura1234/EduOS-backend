"""
Auth token models.

Stores issued tokens, OTPs, and invite links for:
  - JWT refresh token tracking (for logout / revocation)
  - OTP-based password reset
  - First-time onboarding invite links
"""

import uuid
from datetime import timedelta

from django.db import models
from django.utils import timezone

from apps.core.models import BaseModel


def default_otp_expiry():
    """OTPs expire in 5 minutes."""
    return timezone.now() + timedelta(minutes=5)


def default_invite_expiry():
    """Invite links expire in 48 hours."""
    return timezone.now() + timedelta(hours=48)


def default_refresh_expiry():
    """Refresh tokens expire in 7 days."""
    return timezone.now() + timedelta(days=7)


class RefreshToken(BaseModel):
    """
    Tracks issued JWT refresh tokens.

    Allows logout (token revocation) and prevents replay attacks.
    When a user logs out, their token is deleted from this table.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="refresh_tokens",
    )
    token = models.CharField(max_length=512, unique=True, db_index=True)
    expires_at = models.DateTimeField(default=default_refresh_expiry)
    device_info = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    is_revoked = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "accounts_refresh_token"
        verbose_name = "Refresh Token"
        verbose_name_plural = "Refresh Tokens"

    def __str__(self):
        return f"RefreshToken({self.user.full_name}, revoked={self.is_revoked})"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_revoked and not self.is_expired


class OTPRecord(BaseModel):
    """
    Stores OTPs for phone-based password reset.

    Business rules:
      - Max 3 OTPs per phone per 30-minute window.
      - Each OTP expires in 5 minutes.
      - Once used, is_used=True and cannot be reused.
      - We store a hash of the OTP, never the plain text.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="otp_records",
    )
    # We store the hashed OTP, NOT the plain text
    otp_hash = models.CharField(max_length=256)
    phone = models.CharField(max_length=20, db_index=True)
    expires_at = models.DateTimeField(default=default_otp_expiry)
    is_used = models.BooleanField(default=False, db_index=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "accounts_otp_record"
        verbose_name = "OTP Record"
        verbose_name_plural = "OTP Records"
        indexes = [
            models.Index(fields=["phone", "is_used", "expires_at"]),
        ]

    def __str__(self):
        return f"OTPRecord(phone={self.phone}, used={self.is_used})"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired


class InviteToken(BaseModel):
    """
    Stores first-time onboarding invite links.

    When a new Faculty/Student/Parent is created, an invite token is
    generated and sent via SMS. The user clicks the link to set their
    first password. After use, the token is marked as used.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="invite_tokens",
    )
    token = models.UUIDField(default=uuid.uuid4, unique=True, db_index=True)
    expires_at = models.DateTimeField(default=default_invite_expiry)
    is_used = models.BooleanField(default=False, db_index=True)
    sent_to_phone = models.CharField(max_length=20, blank=True, default="")

    class Meta:
        db_table = "accounts_invite_token"
        verbose_name = "Invite Token"
        verbose_name_plural = "Invite Tokens"

    def __str__(self):
        return f"InviteToken({self.user.full_name}, used={self.is_used})"

    @property
    def is_expired(self):
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_used and not self.is_expired
