"""Queries — AuditLog (append-only, hash-chained) + SupportModeLog.

Only insert + read helpers exist: there is intentionally NO update/delete for AuditLog,
which is how immutability (F-239) is enforced at the queries layer.
"""

import hashlib
import json

from apps.analytics.models import AuditLog, SupportModeLog


def canonical_row_hash(*, tenant_id, actor_user_id, action, entity_type, entity_id, diff,
                       prev_hash) -> str:
    """SHA-256 of the canonical audit fields + prev_hash (the chain link)."""
    payload = json.dumps(
        {
            "tenant": str(tenant_id),
            "actor": str(actor_user_id) if actor_user_id else None,
            "action": action,
            "entityType": entity_type or "",
            "entityId": str(entity_id or ""),
            "diff": diff or {},
            "prev": prev_hash or "",
        },
        sort_keys=True, separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def last_hash_for_tenant(tenant_id) -> str:
    """Row-locked last hash in the tenant's chain (prevents concurrent forks)."""
    last = (
        AuditLog.objects.select_for_update()
        .filter(tenant_id=tenant_id)
        .order_by("-created_at")
        .first()
    )
    return last.row_hash if last else ""


def insert_audit(*, tenant, actor, action, entity_type="", entity_id="", diff=None,
                 ip_address=None, user_agent="", correlation_id="") -> AuditLog:
    prev = last_hash_for_tenant(tenant.pk)
    row_hash = canonical_row_hash(
        tenant_id=tenant.pk, actor_user_id=(actor.pk if actor else None), action=action,
        entity_type=entity_type, entity_id=entity_id, diff=diff or {}, prev_hash=prev,
    )
    return AuditLog.objects.create(
        tenant=tenant, actor_user=actor, action=action, entity_type=entity_type,
        entity_id=str(entity_id or ""), diff=diff or {}, ip_address=ip_address,
        user_agent=user_agent, correlation_id=correlation_id,
        prev_hash=prev, row_hash=row_hash,
    )


def list_audit(tenant_id, *, action=None, limit=50, before=None):
    qs = AuditLog.objects.filter(tenant_id=tenant_id).select_related("actor_user").order_by(
        "-created_at"
    )
    if action:
        qs = qs.filter(action=action)
    if before:
        qs = qs.filter(created_at__lt=before)
    return qs[:limit]


def chain_rows(tenant_id):
    """All rows in chain order (for verification)."""
    return AuditLog.objects.filter(tenant_id=tenant_id).order_by("created_at")


# ── Support mode (F-240) ──────────────────────────────────────────────────────
def create_support_session(*, platform_owner, tenant, started_at, reason="", ticket_ref="",
                           read_only=True) -> SupportModeLog:
    return SupportModeLog.objects.create(
        platform_owner=platform_owner, tenant=tenant, started_at=started_at, reason=reason,
        ticket_ref=ticket_ref, read_only=read_only,
    )


def list_support_sessions(tenant_id):
    return SupportModeLog.objects.filter(tenant_id=tenant_id).order_by("-started_at")
