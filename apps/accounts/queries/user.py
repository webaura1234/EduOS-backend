"""
Queries — user and token lookups.

Pure database access functions. No business logic here.
Callers (interactors) are responsible for interpreting the results.
"""

import logging
from datetime import timedelta

from django.utils import timezone

import uuid

from apps.accounts.models.security import LoginAttempt
from apps.accounts.models.token import InviteToken, OTPRecord, RefreshToken
from apps.accounts.models.user import PHONE_LOGIN_ROLES, User
from apps.accounts.phone import phone_lookup_values

logger = logging.getLogger("apps.accounts.queries.user")


# ─────────────────────────────────────────────────────────────────────────────
# User lookups
# ─────────────────────────────────────────────────────────────────────────────

def get_user_by_id(user_id) -> User | None:
    """Return an active User by primary key (UUID), or None."""
    try:
        return User.objects.select_related("tenant", "branch").get(
            pk=user_id, is_active=True
        )
    except User.DoesNotExist:
        return None


def list_admins_in_tenant(tenant_id):
    """Branch-admin users in a tenant (super-admin admin-management screen)."""
    from apps.accounts.models.user import Role
    return (
        User.objects.filter(tenant_id=tenant_id, role=Role.ADMIN)
        .select_related("branch")
        .order_by("first_name", "last_name")
    )


def get_admin_in_tenant(tenant_id, admin_id) -> User | None:
    from apps.accounts.models.user import Role
    try:
        return User.objects.select_related("branch").get(
            pk=admin_id, tenant_id=tenant_id, role=Role.ADMIN
        )
    except (User.DoesNotExist, ValueError, TypeError):
        return None


def set_user_active(user, is_active: bool) -> User:
    user.is_active = is_active
    user.save(update_fields=["is_active"])
    return user


def set_user_branch(user, branch_id) -> User:
    user.branch_id = branch_id
    user.save(update_fields=["branch"])
    return user


def list_linked_accounts(user) -> list[User]:
    """Other active User rows sharing this user's linked_user_group_id (multi-role person).

    Returns [] when the user isn't part of a linked group.
    """
    if not user.linked_user_group_id:
        return []
    return list(
        User.objects.select_related("tenant", "branch")
        .filter(linked_user_group_id=user.linked_user_group_id, is_active=True)
        .exclude(pk=user.pk)
        .order_by("role")
    )


def get_linked_account(user, target_user_id) -> User | None:
    """The active linked account `target_user_id` only if it shares this user's group."""
    if not user.linked_user_group_id:
        return None
    try:
        return User.objects.select_related("tenant", "branch").get(
            pk=target_user_id,
            linked_user_group_id=user.linked_user_group_id,
            is_active=True,
        )
    except (User.DoesNotExist, ValueError, TypeError):
        return None


def get_user_by_phone(phone: str, tenant_id: str) -> User | None:
    """Return an active User matching phone + tenant, or None."""
    try:
        return User.objects.select_related("tenant", "branch").get(
            phone=phone, tenant_id=tenant_id, is_active=True
        )
    except User.DoesNotExist:
        return None


def get_user_by_custom_login_id(custom_login_id: str, tenant_id: str) -> User | None:
    """Return an active User matching custom_login_id + tenant, or None."""
    try:
        return User.objects.select_related("tenant", "branch").get(
            custom_login_id=custom_login_id, tenant_id=tenant_id, is_active=True
        )
    except User.DoesNotExist:
        return None


def get_user_for_token(user_id) -> User | None:
    """Fetch a user by id for JWT authentication, regardless of is_active state.

    The caller (JWTAuthentication) decides how to treat inactive users so it can
    return the right error (EC-AUTH-10).
    """
    try:
        return User.objects.select_related("tenant", "branch").get(pk=user_id)
    except (User.DoesNotExist, ValueError, TypeError):
        return None


def get_user_in_tenant(user_id, tenant_id) -> User | None:
    """Fetch a user by id constrained to a tenant (admin actions on their own tenant)."""
    try:
        return User.objects.select_related("tenant", "branch").get(
            pk=user_id, tenant_id=tenant_id
        )
    except (User.DoesNotExist, ValueError, TypeError):
        return None


def get_phone_login_candidates(phone: str, tenant_id: str) -> list[User]:
    """Active users in a tenant who log in with this phone (admin/super_admin/parent).

    Used for login disambiguation (EC-AUTH-11).
    """
    return list(
        User.objects.select_related("tenant").filter(
            phone__in=phone_lookup_values(phone),
            tenant_id=tenant_id,
            role__in=PHONE_LOGIN_ROLES,
            is_active=True,
        )
    )


def get_reset_candidates(phone: str, tenant_id: str) -> list[User]:
    """All active users in a tenant whose registered phone matches.

    Includes faculty/student (whose `phone` may be a guardian's) for password-reset
    disambiguation (EC-AUTH-12 / EC-AUTH-20).
    """
    return list(
        User.objects.select_related("tenant").filter(
            phone__in=phone_lookup_values(phone),
            tenant_id=tenant_id,
            is_active=True,
        )
    )


def get_users_by_phone_in_tenant(phone: str, tenant_id: str) -> list[User]:
    """All users (any state/role) in a tenant with this phone — for invite linking (EC-AUTH-13)."""
    return list(User.objects.filter(phone__in=phone_lookup_values(phone), tenant_id=tenant_id))


def get_users_by_email_in_tenant(email: str, tenant_id: str) -> list[User]:
    """All users (any state/role) in a tenant with this email — for invite linking (EC-AUTH-13)."""
    if not email:
        return []
    return list(User.objects.filter(email__iexact=email.strip(), tenant_id=tenant_id))


def count_active_by_role_in_tenant(tenant_id, role: str) -> int:
    """Count active users of a given role within a tenant (e.g. students)."""
    return User.objects.filter(tenant_id=tenant_id, role=role, is_active=True).count()


def get_active_user_in_tenant_with_role(tenant_id, user_id, role: str) -> User | None:
    """Fetch a single active user of a given role within a tenant, or None."""
    try:
        return User.objects.get(pk=user_id, tenant_id=tenant_id, role=role, is_active=True)
    except (User.DoesNotExist, ValueError, TypeError):
        return None


def get_first_user_by_role_in_tenant(tenant_id, role: str) -> User | None:
    """Return the earliest-created user of a role in a tenant (e.g. the super-admin)."""
    return (
        User.objects.filter(tenant_id=tenant_id, role=role)
        .order_by("date_joined")
        .first()
    )


def assign_linked_group(users: list[User], group_id: uuid.UUID) -> None:
    """Set linked_user_group_id on each user (EC-AUTH-13)."""
    for user in users:
        if user.linked_user_group_id != group_id:
            user.linked_user_group_id = group_id
            user.save(update_fields=["linked_user_group_id"])


def get_active_user_for_login(
    *,
    tenant_id: str,
    role: str,
    phone: str | None = None,
    custom_login_id: str | None = None,
) -> User | None:
    """
    Resolve a single active User for the authentication backend.

    Exactly one of `phone` / `custom_login_id` should be provided (the backend
    decides which, based on the role). Returns None if no unique match exists.
    """
    base_qs = User.objects.filter(tenant_id=tenant_id, role=role, is_active=True)
    try:
        if phone is not None:
            return base_qs.filter(phone__in=phone_lookup_values(phone)).get()
        if custom_login_id is not None:
            return base_qs.get(custom_login_id=custom_login_id)
        return None
    except User.DoesNotExist:
        return None
    except User.MultipleObjectsReturned:
        logger.error(
            "Multiple users found for login: role=%s tenant=%s phone=%s custom_login_id=%s",
            role, tenant_id, phone, custom_login_id,
        )
        return None


# ─────────────────────────────────────────────────────────────────────────────
# User writes
# ─────────────────────────────────────────────────────────────────────────────

def create_invited_user(
    *,
    first_name: str,
    last_name: str,
    role: str,
    tenant_id,
    branch_id,
    phone: str | None,
    custom_login_id: str | None,
    email: str | None,
    created_by: User | None = None,
) -> User:
    """Create a new User with an unusable password (set later via invite accept)."""
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
    return user


def set_user_password(user: User, raw_password: str) -> None:
    """Hash and persist a new password, clearing the must-change flag."""
    user.set_password(raw_password)
    user.must_change_password = False
    user.save(update_fields=["password", "must_change_password"])


def set_temp_password(user: User, raw_password: str) -> None:
    """Set a temporary password and FORCE a change on next login (EC-AUTH-21)."""
    user.set_password(raw_password)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password"])


# ─────────────────────────────────────────────────────────────────────────────
# Refresh token lookups
# ─────────────────────────────────────────────────────────────────────────────

def get_active_refresh_token(token_str: str) -> RefreshToken | None:
    """
    Return a RefreshToken that is not revoked and not expired, or None.
    """
    try:
        rt = RefreshToken.objects.select_related("user").get(token=token_str)
    except RefreshToken.DoesNotExist:
        return None

    if rt.is_revoked or rt.expires_at < timezone.now():
        return None

    return rt


# ─────────────────────────────────────────────────────────────────────────────
# OTP lookups
# ─────────────────────────────────────────────────────────────────────────────

def get_valid_otp(phone: str) -> OTPRecord | None:
    """
    Return the most recent unused, unexpired OTPRecord for this phone, or None.
    """
    return (
        OTPRecord.objects.filter(
            phone=phone,
            is_used=False,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )


def count_otps_in_window(phone: str, window_minutes: int) -> int:
    """Count OTPs sent to a phone within the last window_minutes."""
    since = timezone.now() - timedelta(minutes=window_minutes)
    return OTPRecord.objects.filter(phone=phone, created_at__gte=since).count()


# ─────────────────────────────────────────────────────────────────────────────
# Invite token lookups
# ─────────────────────────────────────────────────────────────────────────────

def get_valid_invite(token_uuid) -> InviteToken | None:
    """Return a valid (unused, unexpired) InviteToken, or None."""
    try:
        invite = InviteToken.objects.select_related("user").get(token=token_uuid)
    except InviteToken.DoesNotExist:
        return None

    if invite.is_used or invite.expires_at < timezone.now():
        return None

    return invite


def get_invite_by_token(token_uuid) -> InviteToken | None:
    """Return an InviteToken by token regardless of used/expired state, or None.

    Used by the accept flow so it can distinguish 'used' from 'expired' and return
    the correct 410 (EC-AUTH-08 / EC-AUTH-09).
    """
    try:
        return InviteToken.objects.select_related("user").get(token=token_uuid)
    except InviteToken.DoesNotExist:
        return None


def create_invite_token(user: User, sent_to_phone: str = "", created_by: User | None = None) -> InviteToken:
    """Create and return an InviteToken for a user."""
    return InviteToken.objects.create(
        user=user, sent_to_phone=sent_to_phone,
        created_by=created_by, updated_by=created_by,
    )


def mark_invite_used(invite: InviteToken) -> None:
    """Mark an InviteToken as used and stamp used_at (EC-AUTH-08)."""
    invite.is_used = True
    invite.used_at = timezone.now()
    invite.save(update_fields=["is_used", "used_at", "updated_at"])


# ─────────────────────────────────────────────────────────────────────────────
# OTP writes
# ─────────────────────────────────────────────────────────────────────────────

def create_otp_record(user: User, otp_hash: str, phone: str, expires_at) -> OTPRecord:
    """Create and return an OTPRecord."""
    return OTPRecord.objects.create(
        user=user,
        otp_hash=otp_hash,
        phone=phone,
        expires_at=expires_at,
    )


def increment_otp_attempt(otp_record: OTPRecord) -> None:
    """Increment the failed-attempt counter on an OTPRecord."""
    otp_record.attempt_count += 1
    otp_record.save(update_fields=["attempt_count", "updated_at"])


def mark_otp_used(otp_record: OTPRecord) -> None:
    """Mark an OTPRecord as used."""
    otp_record.is_used = True
    otp_record.save(update_fields=["is_used", "updated_at"])


# ─────────────────────────────────────────────────────────────────────────────
# Login attempt lookups
# ─────────────────────────────────────────────────────────────────────────────

def count_failed_attempts(identifier: str, tenant_id: str, window_minutes: int) -> int:
    """Count failed login attempts for identifier+tenant in the last window_minutes.

    Fallback counter for identifiers that don't resolve to a user (enumeration spam).
    """
    since = timezone.now() - timedelta(minutes=window_minutes)
    return LoginAttempt.objects.filter(
        identifier=identifier,
        tenant_id=tenant_id,
        user__isnull=True,
        was_successful=False,
        created_at__gte=since,
    ).count()


def count_failed_attempts_for_user(user_id, window_minutes: int) -> int:
    """Count failed login attempts scoped to a specific user (EC-AUTH-25)."""
    since = timezone.now() - timedelta(minutes=window_minutes)
    return LoginAttempt.objects.filter(
        user_id=user_id,
        was_successful=False,
        created_at__gte=since,
    ).count()


def record_login_attempt(
    identifier: str,
    tenant_id: str,
    ip_address: str,
    was_successful: bool,
    failure_reason: str = "",
    user: User | None = None,
) -> LoginAttempt:
    """Create and return a LoginAttempt record (optionally tied to a resolved user)."""
    return LoginAttempt.objects.create(
        identifier=identifier,
        tenant_id=tenant_id,
        ip_address=ip_address,
        was_successful=was_successful,
        failure_reason=failure_reason,
        user=user,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Admin user-management screen
# ─────────────────────────────────────────────────────────────────────────────

def list_managed_users(tenant_id):
    """All manageable users (admin/faculty/student/parent) in a tenant."""
    from apps.accounts.models.user import Role

    return (
        User.objects.filter(
            tenant_id=tenant_id,
            role__in=[Role.ADMIN, Role.FACULTY, Role.STUDENT, Role.PARENT],
        )
        .select_related("branch")
        .order_by("role", "first_name", "last_name")
    )


def list_pending_invites(tenant_id):
    """Unused invite tokens for users in a tenant, newest first."""
    return (
        InviteToken.objects.filter(user__tenant_id=tenant_id, is_used=False)
        .select_related("user")
        .order_by("-created_at")
    )


def get_managed_user(tenant_id, user_id) -> User | None:
    """Fetch a user in a tenant regardless of active state (for admin actions)."""
    try:
        return User.objects.select_related("branch").get(
            pk=user_id, tenant_id=tenant_id
        )
    except (User.DoesNotExist, ValueError, TypeError):
        return None


def hard_delete_user(user) -> None:
    """Permanently remove a user row (admin hard-delete of a student)."""
    user.delete()
