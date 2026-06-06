"""
Invite interactor — create invite and accept invite.

Step 1 (Admin): create_and_send_invite
  Admin creates a new User (faculty/student/parent) and sends them
  an invite link via SMS so they can set their first password.

Step 2 (New User): accept_invite
  New user clicks the invite link, sets their password, and is
  immediately issued a token pair so they are logged in.
"""

import logging
import uuid

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.accounts.dtos import InviteAcceptedDTO, InviteCreatedDTO
from apps.core.exceptions import GoneError

from apps.accounts.models.user import Role, User
from apps.accounts.queries.user import (
    assign_linked_group,
    create_invite_token,
    create_invited_user,
    get_invite_by_token,
    get_users_by_phone_in_tenant,
    mark_invite_used,
    set_user_password,
)
from apps.accounts.sms import send_sms
from apps.accounts.tokens import generate_access_token, generate_refresh_token
from apps.accounts.validators import validate_password_strength

logger = logging.getLogger("apps.accounts.interactors.invite")

# Roles that can be invited (never invite super_admin via this flow)
INVITABLE_ROLES = {Role.FACULTY, Role.STUDENT, Role.PARENT, Role.ADMIN}


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Admin creates user + invite
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def create_and_send_invite(
    *,
    created_by: User,
    role: str,
    first_name: str,
    last_name: str = "",
    phone: str = None,
    custom_login_id: str = None,
    email: str = None,
    tenant_id,
    branch_id=None,
) -> InviteCreatedDTO:
    """
    Create a new User and issue an InviteToken sent via SMS.

    Rules:
      - Only admin or super_admin can call this.
      - Role must be in INVITABLE_ROLES.
      - phone required for parent/admin roles.
      - custom_login_id required for faculty/student roles.
      - User is created with an unusable temporary password (must change on invite accept).

    Returns dict with user_id and invite_token.

    Raises ValidationError or PermissionDenied on invalid input.
    """
    # Permission check
    if created_by.role not in {Role.ADMIN, Role.SUPER_ADMIN}:
        raise PermissionDenied("Only admins can create invites.")

    if role not in INVITABLE_ROLES:
        raise ValidationError(f"Role '{role}' cannot be invited via this endpoint.")

    # Validate identifier presence
    if role in {Role.PARENT, Role.ADMIN} and not phone:
        raise ValidationError("Phone number is required for this role.")
    if role in {Role.FACULTY, Role.STUDENT} and not custom_login_id:
        raise ValidationError("Custom login ID (Employee ID / Roll Number) is required for this role.")

    # EC-AUTH-13: detect an existing account on this phone in the same tenant.
    existing_on_phone = get_users_by_phone_in_tenant(phone, tenant_id) if phone else []

    # Create user with unusable password (must_change_password=True by default)
    user = create_invited_user(
        first_name=first_name,
        last_name=last_name,
        role=role,
        tenant_id=tenant_id,
        branch_id=branch_id,
        phone=phone,
        custom_login_id=custom_login_id,
        email=email,
    )

    # EC-AUTH-13: link the new account to the existing one(s) sharing this phone.
    linked_account_created = False
    if existing_on_phone:
        group_id = next(
            (u.linked_user_group_id for u in existing_on_phone if u.linked_user_group_id),
            uuid.uuid4(),
        )
        assign_linked_group([*existing_on_phone, user], group_id)
        linked_account_created = True
        logger.info("Linked account created: new=%s group=%s", user.id, group_id)

    # Create invite token
    invite = create_invite_token(user=user, sent_to_phone=phone or "")

    # Send invite SMS (failures are tolerated — admin can resend)
    _send_invite_sms(phone=phone, token=str(invite.token), user=user)

    logger.info(
        "Invite created: user=%s role=%s by=%s", user.id, role, created_by.id
    )

    return InviteCreatedDTO(
        user_id=user.id,
        invite_token=invite.token,
        linked_account_created=linked_account_created,
    )


def _send_invite_sms(phone: str, token: str, user: User) -> None:
    """Send the invite link via the circuit-breaker-protected dispatcher.

    Failures are swallowed: the user is still created and the admin can resend.
    """
    if not phone:
        return

    invite_url = f"https://app.eduos.in/invite/{token}"  # configurable later
    try:
        send_sms(
            phone,
            f"Welcome to EduOS! Set your password here: {invite_url} (expires in 48 hours)",
        )
    except Exception as exc:  # noqa: BLE001 — invite send is best-effort
        logger.error("Failed to send invite SMS to %s: %s", phone, exc)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — New user accepts invite
# ─────────────────────────────────────────────────────────────────────────────

@transaction.atomic
def accept_invite(
    token_uuid,
    new_password: str,
    device_info: str = "",
    ip_address: str = None,
) -> InviteAcceptedDTO:
    """
    Accept an invite: validate token, set password, return token pair.

    The user is immediately logged in after accepting the invite.

    Raises:
      AuthenticationFailed — token invalid or expired.
      ValidationError      — password doesn't meet strength requirements.
    """
    # Look up the invite, distinguishing invalid vs used vs expired (EC-AUTH-08/09)
    invite = get_invite_by_token(token_uuid)
    if invite is None:
        raise AuthenticationFailed("Invite link is invalid.")
    if invite.is_used:
        raise GoneError("This invite link has already been used.")
    if invite.expires_at < timezone.now():
        raise GoneError("This invite link has expired.")

    user = invite.user

    # Validate password strength
    try:
        validate_password_strength(new_password)
    except ValidationError as exc:
        raise ValidationError(exc.messages)

    # Set password
    set_user_password(user, new_password)

    # Mark invite as used
    mark_invite_used(invite)

    # Issue token pair — user is now logged in
    access_token = generate_access_token(user)
    refresh_token_str, _ = generate_refresh_token(
        user=user,
        device_info=device_info,
        ip_address=ip_address,
    )

    logger.info("Invite accepted: user=%s role=%s", user.id, user.role)

    return InviteAcceptedDTO(
        access=access_token,
        refresh=refresh_token_str,
        user_id=user.id,
        role=user.role,
    )
