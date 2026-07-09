"""Multi-role account linking rules (same physical person, multiple User rows).

Per product spec (auth.md §4), only specific role pairs may share
linked_user_group_id. Guardian phone on a student record is contact info only —
student↔parent must use StudentGuardianLink, not linked_user_group_id.
"""

from __future__ import annotations

from apps.accounts.models.user import Role, User

# Valid same-person pairs that may share linked_user_group_id via phone/email match.
LINKABLE_ROLE_PAIRS: frozenset[frozenset[str]] = frozenset({
    frozenset({Role.ADMIN, Role.PARENT}),
    frozenset({Role.SUPER_ADMIN, Role.PARENT}),
    frozenset({Role.FACULTY, Role.PARENT}),
})


def is_linkable_role_pair(role_a: str, role_b: str) -> bool:
    """True when two roles may belong to the same person (linked_user_group_id)."""
    if role_a == role_b:
        return False
    return frozenset({role_a, role_b}) in LINKABLE_ROLE_PAIRS


def filter_linkable_users(users: list[User], target_role: str) -> list[User]:
    """Keep users whose role forms a valid linkable pair with target_role."""
    return [u for u in users if is_linkable_role_pair(target_role, u.role)]


def has_linked_accounts(user: User) -> bool:
    """True when another active user in the tenant shares linked_user_group_id
    and forms a valid multi-role pair (not guardian/student phone overlap)."""
    if not user.linked_user_group_id:
        return False
    peers = (
        User.objects.filter(
            linked_user_group_id=user.linked_user_group_id,
            tenant_id=user.tenant_id,
            is_active=True,
        )
        .exclude(pk=user.pk)
    )
    return any(is_linkable_role_pair(user.role, peer.role) for peer in peers)
