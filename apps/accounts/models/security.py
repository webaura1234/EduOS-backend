"""
Security and authentication models.

  - LoginAttempt → tracks every login attempt for brute-force protection.
                   After MAX_LOGIN_ATTEMPTS failures in a window, the
                   identifier is locked out for LOCKOUT_DURATION minutes.
"""

from django.db import models

from apps.core.models import BaseModel


class LoginAttempt(BaseModel):
    """
    Record of every login attempt (success or failure) for an identifier.

    Used to enforce brute-force lockout:
      - 5 failed attempts from the same identifier + tenant in 30 min
        → lockout for 15 min.

    identifier is either a phone number or a custom_login_id depending
    on the role attempting login.
    """

    identifier = models.CharField(
        max_length=100,
        db_index=True,
        help_text="Phone number or custom_login_id used in the attempt.",
    )
    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.CASCADE,
        related_name="login_attempts",
        null=True,
        blank=True,
        help_text="Tenant scope for the login attempt.",
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        db_index=True,
    )
    was_successful = models.BooleanField(default=False, db_index=True)
    failure_reason = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text=(
            "Reason for failure: 'wrong_password', 'user_not_found', "
            "'account_inactive', 'locked_out'."
        ),
    )

    class Meta:
        db_table = "accounts_login_attempt"
        verbose_name = "Login Attempt"
        verbose_name_plural = "Login Attempts"
        indexes = [
            models.Index(fields=["identifier", "tenant", "was_successful", "created_at"]),
        ]
        # BaseModel.created_at gives us the timestamp

    def __str__(self):
        status = "✓" if self.was_successful else "✗"
        return f"LoginAttempt {status} {self.identifier} @ {self.created_at}"
