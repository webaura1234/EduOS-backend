"""Interactors — central audit logging + chain verification (F-239 / EC-PRIV-06)."""

from apps.analytics.queries import audit as audit_q


def record_audit(*, tenant, actor, action, entity_type="", entity_id="", diff=None,
                 request=None):
    """Append a hash-chained audit row. Call inside the caller's transaction so the audit
    commits atomically with the action it records."""
    ip = ua = corr = None
    if request is not None:
        ip = request.META.get("REMOTE_ADDR")
        ua = request.META.get("HTTP_USER_AGENT", "")
        corr = request.headers.get("X-Request-Id", "") if hasattr(request, "headers") else ""
    return audit_q.insert_audit(
        tenant=tenant, actor=actor, action=action, entity_type=entity_type,
        entity_id=entity_id, diff=diff or {}, ip_address=ip, user_agent=ua or "",
        correlation_id=corr or "",
    )


def verify_chain(tenant_id) -> dict:
    """Walk the tenant's audit chain and recompute hashes; detect any tamper/fork."""
    prev = ""
    count = 0
    for row in audit_q.chain_rows(tenant_id):
        expected = audit_q.canonical_row_hash(
            tenant_id=row.tenant_id, actor_user_id=row.actor_user_id, action=row.action,
            entity_type=row.entity_type, entity_id=row.entity_id, diff=row.diff,
            prev_hash=prev,
        )
        if row.prev_hash != prev or row.row_hash != expected:
            return {"valid": False, "brokenAt": str(row.pk), "verified": count}
        prev = row.row_hash
        count += 1
    return {"valid": True, "verified": count}
