"""
Data Transfer Objects (DTOs) for the accounts app.

DTOs are the typed contract between interactors and views.
Interactors return DTOs — never raw dicts.
Views read DTO fields and build HTTP responses.

Rules:
  - Use @dataclass for all DTOs.
  - Store proper Python types (uuid.UUID, bool, str).
  - Call .to_dict() when passing to DRF Response().
  - Never import models here — DTOs are pure data containers.
"""

import datetime
import uuid
from dataclasses import dataclass, field


# ─────────────────────────────────────────────────────────────────────────────
# Auth DTOs
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class LoginResponseDTO:
    """
    Returned by interactors.auth.login().
    Carries the token pair plus user context for the client.
    """
    access: str
    refresh: str
    must_change_password: bool
    user_id: uuid.UUID
    role: str

    def to_dict(self) -> dict:
        return {
            "access": self.access,
            "refresh": self.refresh,
            "must_change_password": self.must_change_password,
            "user_id": str(self.user_id),
            "role": self.role,
        }


@dataclass
class MFARequiredDTO:
    """
    Returned when email OTP is required to complete login (admin, super_admin,
    platform_owner). Client POSTs OTP to /api/v1/auth/mfa/verify/.
    """
    mfa_session_token: str
    email_hint: str
    has_parent_account: bool = False

    def to_dict(self) -> dict:
        return {
            "mfa_required": True,
            "mfa_session_token": self.mfa_session_token,
            "email_hint": self.email_hint,
            "has_parent_account": self.has_parent_account,
        }


@dataclass
class OtpLoginPasswordRequiredDTO:
    """No privileged account for phone OTP — client should collect password (parent)."""

    has_parent_account: bool = False

    def to_dict(self) -> dict:
        return {
            "password_required": True,
            "has_parent_account": self.has_parent_account,
            "message": "Continue with your password to sign in.",
        }


@dataclass
class OtpLoginDisambiguationDTO:
    """Multiple privileged accounts share this phone — pick one before OTP is sent."""

    accounts: list
    has_parent_account: bool = False

    def to_dict(self) -> dict:
        return {
            "disambiguation": True,
            "accounts": self.accounts,
            "has_parent_account": self.has_parent_account,
        }


@dataclass
class LoginResolutionDTO:
    """
    Returned by interactors.auth.disambiguate_login().

    Either:
      - requires_selection=True with `accounts` (role picker, EC-AUTH-11), or
      - `login` populated with a LoginResponseDTO (single match → logged in).
    """
    login: "LoginResponseDTO | None" = None
    requires_selection: bool = False
    accounts: list | None = None

    def to_dict(self) -> dict:
        if self.requires_selection:
            return {
                "requires_selection": True,
                "accounts": self.accounts or [],
            }
        return {
            "requires_selection": False,
            **(self.login.to_dict() if self.login else {}),
        }


@dataclass
class TokenPairDTO:
    """
    Returned by interactors.auth.refresh_tokens().
    Contains only the new access + refresh pair (no user data needed —
    client already knows who they are).
    """
    access: str
    refresh: str

    def to_dict(self) -> dict:
        return {
            "access": self.access,
            "refresh": self.refresh,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Invite DTOs
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class InviteCreatedDTO:
    """
    Returned by interactors.invite.create_and_send_invite().
    Admin receives the created user ID and the invite token for reference.
    """
    user_id: uuid.UUID
    invite_token: uuid.UUID
    linked_account_created: bool = False

    def to_dict(self) -> dict:
        return {
            "user_id": str(self.user_id),
            "invite_token": str(self.invite_token),
            "linked_account_created": self.linked_account_created,
        }


@dataclass
class InviteAcceptedDTO:
    """
    Returned by interactors.invite.accept_invite().
    Same shape as LoginResponseDTO — user is immediately logged in
    after accepting their invite and setting their first password.
    """
    access: str
    refresh: str
    user_id: uuid.UUID
    role: str
    must_change_password: bool = False  # always False after invite accept

    def to_dict(self) -> dict:
        return {
            "access": self.access,
            "refresh": self.refresh,
            "user_id": str(self.user_id),
            "role": self.role,
            "must_change_password": self.must_change_password,
        }


# ─────────────────────────────────────────────────────────────────────────────
# General DTOs
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MessageDTO:
    """
    Returned by views/interactors that only need to return a status message.
    """
    detail: str

    def to_dict(self) -> dict:
        return {
            "detail": self.detail,
        }


@dataclass
class UserProfileDTO:
    """
    Returned by MeView.
    """
    id: uuid.UUID
    role: str
    full_name: str
    email: str | None
    phone: str | None
    tenant_id: uuid.UUID | None
    branch_id: uuid.UUID | None
    must_change_password: bool
    date_joined: datetime.datetime
    custom_login_id: str | None = None
    linked_user_group_id: uuid.UUID | None = None
    institution_type: str | None = None
    tenant_subdomain: str | None = None
    avatar_url: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "role": self.role,
            "full_name": self.full_name,
            "email": self.email,
            "phone": self.phone,
            "tenant_id": str(self.tenant_id) if self.tenant_id else None,
            "branch_id": str(self.branch_id) if self.branch_id else None,
            "must_change_password": self.must_change_password,
            "date_joined": self.date_joined.isoformat() if hasattr(self.date_joined, "isoformat") else str(self.date_joined),
            "custom_login_id": self.custom_login_id,
            "linked_user_group_id": str(self.linked_user_group_id) if self.linked_user_group_id else None,
            "institution_type": self.institution_type,
            "tenant_subdomain": self.tenant_subdomain,
            "avatarUrl": self.avatar_url,
        }

