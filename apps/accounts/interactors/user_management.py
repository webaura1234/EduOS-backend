"""Admin user-management write actions — deactivate, activate, reset, invite, delete, promote.

All functions are tenant-scoped (the acting admin can only touch their own tenant)
and return the exact dict shapes the admin Users screen consumes (ManagedUser /
UserInvite), so the frontend route handlers are thin passthroughs.
"""

import uuid

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.interactors.password import admin_reset_password
from apps.accounts.models.user import Role
from apps.accounts.queries import user as uq

MULTI_ROLE_POLICY = (
    "Faculty and parent (or other role combinations) use separate accounts "
    "linked by the same phone number or email."
)


# ── Shared mappers (also used by the GET aggregate view) ─────────────────────

def managed_user_dict(user, invite=None) -> dict:
    if invite is None:
        invite_status = "none"
    elif invite.expires_at < timezone.now():
        invite_status = "expired"
    else:
        invite_status = "pending"

    updated = getattr(user, "updated_at", None)
    return {
        "id": str(user.id),
        "name": user.full_name,
        "email": user.email or "",
        "phone": user.phone,
        "role": user.role,
        "custom_login_id": user.custom_login_id,
        "linked_user_group_id": (
            str(user.linked_user_group_id) if user.linked_user_group_id else None
        ),
        "branch": str(user.branch_id) if user.branch_id else None,
        "is_active": user.is_active,
        "invite_status": invite_status,
        "password_reset_required": user.must_change_password,
        "created_at": user.date_joined.isoformat(),
        "updated_at": updated.isoformat() if updated else user.date_joined.isoformat(),
    }


def invite_dict(invite) -> dict:
    return {
        "id": str(invite.id),
        "user_id": str(invite.user_id),
        "email": invite.user.email or "",
        "token": str(invite.token),
        "invite_url": f"/invite/accept?token={invite.token}",
        "created_at": invite.created_at.isoformat(),
        "expires_at": invite.expires_at.isoformat(),
        "used_at": invite.used_at.isoformat() if invite.used_at else None,
    }


def _require_user(tenant_id, user_id, *, branch_id=None):
    user = uq.get_managed_user(tenant_id, user_id)
    if user is None:
        raise NotFound("User not found.")
    if branch_id and user.branch_id != branch_id:
        raise NotFound("User not found.")
    return user


# ── Actions ──────────────────────────────────────────────────────────────────

@transaction.atomic
def set_active(*, admin, user_id, is_active: bool) -> dict:
    user = _require_user(admin.tenant_id, user_id, branch_id=admin.branch_id)
    uq.set_user_active(user, is_active)
    return managed_user_dict(user)


@transaction.atomic
def send_invite(*, admin, user_id) -> dict:
    user = _require_user(admin.tenant_id, user_id, branch_id=admin.branch_id)
    if not user.email and not user.phone:
        raise ValidationError("User has no email or phone to send an invite to.")
    invite = uq.create_invite_token(user, sent_to_phone=user.phone or "")
    return invite_dict(invite)


def reset_password(*, admin, user_id) -> dict:
    user = _require_user(admin.tenant_id, user_id, branch_id=admin.branch_id)
    temp = admin_reset_password(admin=admin, target_user_id=str(user.id))
    user.refresh_from_db()
    return {"user": managed_user_dict(user), "temporary_password": temp}


@transaction.atomic
def hard_delete_student(*, admin, user_id) -> dict:
    from apps.fees.queries.invoice import list_dues_for_student_user

    user = _require_user(admin.tenant_id, user_id, branch_id=admin.branch_id)
    if user.role != Role.STUDENT:
        raise ValidationError("Only student accounts can be hard-deleted.")

    open_paise = sum(inv.balance_paise for inv in list_dues_for_student_user(user.id))
    if open_paise > 0:
        rupees = open_paise / 100
        raise ValidationError({
            "error": f"Cannot delete this student: open fee dues of ₹{rupees:,.2f} "
                     "must be cleared first.",
            "code": "open_fee_dues",
            "balance": rupees,
        })

    result = {"id": str(user.id), "name": user.full_name}
    uq.hard_delete_user(user)
    return result


@transaction.atomic
def promote_student_to_faculty(*, admin, user_id) -> dict:
    student = _require_user(admin.tenant_id, user_id, branch_id=admin.branch_id)
    if student.role != Role.STUDENT:
        raise ValidationError("Only student accounts can be promoted.")

    # Link the two accounts so they're recognised as the same person.
    group_id = student.linked_user_group_id or uuid.uuid4()
    if not student.linked_user_group_id:
        student.linked_user_group_id = group_id
        student.save(update_fields=["linked_user_group_id"])

    faculty = uq.create_invited_user(
        first_name=student.first_name,
        last_name=student.last_name,
        role=Role.FACULTY,
        tenant_id=student.tenant_id,
        branch_id=student.branch_id,
        phone=student.phone,
        custom_login_id=f"FAC-{str(uuid.uuid4())[:8].upper()}",
        email=student.email,
        created_by=admin,
    )
    faculty.linked_user_group_id = group_id
    faculty.save(update_fields=["linked_user_group_id"])

    return {
        "student": managed_user_dict(student),
        "faculty": managed_user_dict(faculty),
    }


@transaction.atomic
def update_user(*, admin, user_id, name=None, email=None, phone=None) -> dict:
    user = _require_user(admin.tenant_id, user_id, branch_id=admin.branch_id)
    fields: list[str] = []
    if name is not None and name.strip():
        first, _, last = name.strip().partition(" ")
        user.first_name = first
        user.last_name = last
        fields.extend(["first_name", "last_name"])
    if email is not None:
        user.email = email.strip() or None
        fields.append("email")
    if phone is not None:
        if user.role in {Role.PARENT, Role.ADMIN} and not str(phone).strip():
            raise ValidationError("Phone number is required for this role.")
        user.phone = phone.strip() or None
        fields.append("phone")
    if fields:
        user.save(update_fields=fields)
    return managed_user_dict(user)


def check_multi_role(*, admin, phone, email, role) -> dict | None:
    """Warn if creating this role would collide with an existing person (EC-AUTH-13)."""
    matches = _multi_role_matches(admin.tenant_id, phone, email, role)
    if not matches:
        return None
    group_id = next(
        (str(u.linked_user_group_id) for u in matches if u.linked_user_group_id),
        str(uuid.uuid4()),
    )
    return {
        "existing_accounts": [
            {
                "user_id": str(u.id),
                "name": u.full_name,
                "role": u.role,
                "is_active": u.is_active,
            }
            for u in matches
        ],
        "will_link_by": "phone" if phone else "email",
        "linked_user_group_id": group_id,
    }


def _multi_role_matches(tenant_id, phone, email, role) -> list:
    """Users in tenant sharing this phone/email but holding a different role."""
    seen: dict[str, object] = {}
    if phone:
        for u in uq.get_users_by_phone_in_tenant(phone, tenant_id):
            seen[str(u.id)] = u
    if email:
        for u in uq.get_users_by_email_in_tenant(email, tenant_id):
            seen[str(u.id)] = u
    return [u for u in seen.values() if u.role != role]


@transaction.atomic
def create_user(*, admin, name, email, phone, role, send_invite=True) -> dict:
    tenant_id = admin.tenant_id

    if role in {Role.PARENT, Role.ADMIN} and not phone:
        raise ValidationError("Phone number is required for this role.")

    first, _, last = name.strip().partition(" ")

    # EC-AUTH-13: link to an existing person sharing this phone/email.
    matches = _multi_role_matches(tenant_id, phone, email, role)
    group_id = None
    if matches:
        group_id = next(
            (u.linked_user_group_id for u in matches if u.linked_user_group_id),
            uuid.uuid4(),
        )
        for existing in matches:
            if not existing.linked_user_group_id:
                existing.linked_user_group_id = group_id
                existing.save(update_fields=["linked_user_group_id"])

    custom_login_id = None
    if role in {Role.FACULTY, Role.STUDENT}:
        prefix = "FAC" if role == Role.FACULTY else "STU"
        custom_login_id = f"{prefix}-{str(uuid.uuid4())[:6].upper()}"

    user = uq.create_invited_user(
        first_name=first,
        last_name=last,
        role=role,
        tenant_id=tenant_id,
        branch_id=admin.branch_id,
        phone=phone or None,
        custom_login_id=custom_login_id,
        email=email or None,
        created_by=admin,
    )
    if group_id:
        user.linked_user_group_id = group_id
        user.save(update_fields=["linked_user_group_id"])

    invite = None
    if send_invite:
        invite = uq.create_invite_token(user, sent_to_phone=user.phone or "", created_by=admin)

    return {
        "user": managed_user_dict(user, invite),
        "invite": invite_dict(invite) if invite else None,
    }
