"""
Auth audit logging — fire-and-forget helpers.

All functions swallow exceptions so that an audit log failure never
blocks the actual auth operation. Failures are logged at ERROR level
so they are still visible in monitoring.
"""

import logging

from django.db import connection, transaction

logger = logging.getLogger("apps.accounts.audit")


def _write_auth_event(
    *,
    event: str,
    user=None,
    tenant=None,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> None:
    try:
        from apps.accounts.models.security import AuthAuditLog

        AuthAuditLog.objects.create(
            event=event,
            user=user,
            tenant=tenant if tenant is not None else getattr(user, "tenant", None),
            ip_address=ip_address,
            metadata=metadata or {},
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("Failed to write auth audit log (event=%s): %s", event, exc)


def log_auth_event(
    *,
    event: str,
    user=None,
    tenant=None,
    ip_address: str | None = None,
    metadata: dict | None = None,
) -> None:
    """Write one row to AuthAuditLog. Never raises.

    Deferred until after commit when inside ATOMIC_REQUESTS so a missing
    table or other audit failure cannot poison the login transaction.
    """
    kwargs = {
        "event": event,
        "user": user,
        "tenant": tenant,
        "ip_address": ip_address,
        "metadata": metadata,
    }
    if connection.in_atomic_block:
        transaction.on_commit(lambda: _write_auth_event(**kwargs))
    else:
        _write_auth_event(**kwargs)
