"""
Security and authentication models.

  - LoginAttempt          → tracks every login attempt for brute-force protection.
  - AuthAuditLog          → immutable append-only log of significant auth events.
  - StudentIDCounter      → gap-free sequential student ID per branch per year.
  - PendingIdentityChange → stores phone/email change OTP pending user verification.
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
    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="login_attempts",
        null=True,
        blank=True,
        db_index=True,
        help_text="Resolved user for the attempt, if the identifier matched one. "
                  "Lockout is scoped to this user (EC-AUTH-25).",
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
            models.Index(fields=["user", "was_successful", "created_at"]),
        ]
        # BaseModel.created_at gives us the timestamp

    def __str__(self):
        status = "✓" if self.was_successful else "✗"
        return f"LoginAttempt {status} {self.identifier} @ {self.created_at}"


class AuthAuditLog(BaseModel):
    """
    Immutable append-only log of significant auth events.

    Never update or delete rows — only insert. Provides an audit trail for
    security investigations (who logged in, when, from where, what failed).
    """

    EVENT_CHOICES = [
        ("login_success", "Login Success"),
        ("login_failed", "Login Failed"),
        ("login_locked", "Login Locked"),
        ("mfa_otp_sent", "MFA OTP Sent"),
        ("mfa_verified", "MFA Verified"),
        ("mfa_failed", "MFA Failed"),
        ("logout", "Logout"),
        ("password_changed", "Password Changed"),
        ("password_reset_requested", "Password Reset Requested"),
        ("password_reset_used", "Password Reset Used"),
        ("invite_sent", "Invite Sent"),
        ("invite_accepted", "Invite Accepted"),
    ]

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auth_audit_logs",
        db_index=True,
    )
    tenant = models.ForeignKey(
        "organizations.Tenant",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="auth_audit_logs",
    )
    event = models.CharField(max_length=40, choices=EVENT_CHOICES, db_index=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "accounts_auth_audit_log"
        verbose_name = "Auth Audit Log"
        verbose_name_plural = "Auth Audit Logs"
        indexes = [
            models.Index(fields=["user", "event", "created_at"]),
            models.Index(fields=["tenant", "event", "created_at"]),
        ]

    def __str__(self):
        return f"AuthAuditLog({self.event}, user={self.user_id}) @ {self.created_at}"


class StudentIDCounter(BaseModel):
    """
    Gap-free sequential student ID counter per branch per academic year.

    Used by generate_student_id() to produce deterministic, collision-free
    custom_login_id values for new students (e.g. "ABCS/2025/00142").
    A row-level lock (SELECT FOR UPDATE) prevents duplicates under concurrent admits.
    """

    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="student_id_counters",
        db_index=True,
    )
    academic_year = models.CharField(
        max_length=9,
        help_text="Format: '2025-2026'",
    )
    last_sequence = models.BigIntegerField(default=0)

    class Meta:
        db_table = "accounts_student_id_counter"
        verbose_name = "Student ID Counter"
        verbose_name_plural = "Student ID Counters"
        unique_together = [("branch", "academic_year")]

    def __str__(self):
        return f"StudentIDCounter(branch={self.branch_id}, year={self.academic_year}, seq={self.last_sequence})"


class PendingIdentityChange(BaseModel):
    """
    Stores a phone or email change that is pending OTP verification.

    Flow:
      1. User requests change (new phone/email).
      2. System sends OTP to the new value, stores this record.
      3. User verifies OTP → is_verified=True, user's field updated.

    Any existing unverified record for the same user + change_type is
    cancelled when a new one is created.
    """

    MAX_ATTEMPTS = 3

    CHANGE_TYPE_CHOICES = [
        ("phone", "Phone Number"),
        ("email", "Email Address"),
    ]

    user = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="pending_identity_changes",
        db_index=True,
    )
    change_type = models.CharField(max_length=10, choices=CHANGE_TYPE_CHOICES, db_index=True)
    new_value = models.CharField(max_length=200, help_text="The new phone number or email address.")
    otp_hash = models.CharField(max_length=256)
    expires_at = models.DateTimeField()
    is_verified = models.BooleanField(default=False, db_index=True)
    attempt_count = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "accounts_pending_identity_change"
        verbose_name = "Pending Identity Change"
        verbose_name_plural = "Pending Identity Changes"
        indexes = [
            models.Index(fields=["user", "change_type", "is_verified", "expires_at"]),
        ]

    def __str__(self):
        return f"PendingIdentityChange({self.change_type}, user={self.user_id}, verified={self.is_verified})"

    @property
    def is_expired(self):
        from django.utils import timezone
        return timezone.now() > self.expires_at

    @property
    def is_valid(self):
        return not self.is_verified and not self.is_expired and self.attempt_count < self.MAX_ATTEMPTS
