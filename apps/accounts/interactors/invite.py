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

from django.core.exceptions import ValidationError
from django.db import transaction
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied

from apps.accounts.dtos import InviteAcceptedDTO, InviteCreatedDTO

from apps.accounts.models.token import InviteToken
from apps.accounts.models.user import Role, User
from apps.accounts.queries.user import get_valid_invite
from apps.accounts.queries.session import revoke_all_user_tokens
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

    # Create user with unusable password (must_change_password=True by default)
    user = User(
        first_name=first_name,
        last_name=last_name,
        role=role,
        tenant_id=tenant_id,
        branch_id=branch_id,
        phone=phone,
        custom_login_id=custom_login_id,
        email=email,
        must_change_password=True,
    )
    user.set_unusable_password()
    user.save()

    # Create invite token
    invite = InviteToken.objects.create(
        user=user,
        sent_to_phone=phone or "",
    )

    # Send invite SMS (or log in dev)
    _send_invite_sms(phone=phone, token=str(invite.token), user=user)

    logger.info(
        "Invite created: user=%s role=%s by=%s", user.id, role, created_by.id
    )

    return InviteCreatedDTO(
        user_id=user.id,
        invite_token=invite.token,
    )


def _send_invite_sms(phone: str, token: str, user: User) -> None:
    """Send the invite link via SMS in prod, or log in dev."""
    import django.conf as conf

    invite_url = f"https://app.eduos.in/invite/{token}"  # configurable later

    if conf.settings.DEBUG:
        logger.info(
            "📩 [DEV] Invite for %s (%s): %s",
            user.first_name, phone or "no phone", invite_url,
        )
        return

    # Production: MSG91 SMS
    try:
        import requests
        requests.post(
            "https://api.msg91.com/api/sendhttp.php",
            params={
                "authkey": conf.settings.MSG91_AUTH_KEY,
                "mobiles": phone,
                "message": (
                    f"Welcome to EduOS! Set your password here: {invite_url} "
                    f"(expires in 48 hours)"
                ),
                "sender": conf.settings.MSG91_SENDER_ID,
                "route": "4",
            },
            timeout=10,
        ).raise_for_status()
        logger.info("Invite SMS sent to %s", phone)
    except Exception as exc:
        logger.error("Failed to send invite SMS to %s: %s", phone, exc)
        # Don't raise — user is still created, admin can resend manually


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
    # Look up valid invite
    invite = get_valid_invite(token_uuid)
    if invite is None:
        raise AuthenticationFailed("Invite link is invalid or has expired.")

    user = invite.user

    # Validate password strength
    try:
        validate_password_strength(new_password)
    except ValidationError as exc:
        raise ValidationError(exc.messages)

    # Set password
    user.set_password(new_password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password"])

    # Mark invite as used
    invite.is_used = True
    invite.save(update_fields=["is_used", "updated_at"])

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
