"""Queries — Notification inbox."""

from django.db.models import Q
from django.utils import timezone

from apps.communications.models import Notification


def _active_qs():
    now = timezone.now()
    return Notification.objects.filter(is_active=True).filter(
        Q(expires_at__isnull=True) | Q(expires_at__gt=now)
    )


def list_for_recipient(recipient_id, *, category=None, limit=50, offset=0):
    qs = (
        _active_qs()
        .filter(recipient_id=recipient_id)
        .select_related("branch", "tenant", "created_by")
        .order_by("-created_at")
    )
    if category:
        qs = qs.filter(category=category)
    return qs[offset: offset + limit]


def unread_count(recipient_id) -> int:
    return (
        _active_qs()
        .filter(recipient_id=recipient_id, read_at__isnull=True)
        .count()
    )


def get_for_recipient(recipient_id, notification_id):
    return (
        _active_qs()
        .filter(recipient_id=recipient_id, pk=notification_id)
        .first()
    )


def mark_read(notification, *, user=None) -> Notification:
    if notification.read_at:
        return notification
    notification.read_at = timezone.now()
    update_fields = ["read_at", "updated_at"]
    if user:
        notification.updated_by = user
        update_fields.append("updated_by")
    notification.save(update_fields=update_fields)
    return notification


def mark_all_read(recipient_id, *, user=None) -> int:
    now = timezone.now()
    qs = _active_qs().filter(recipient_id=recipient_id, read_at__isnull=True)
    return qs.update(read_at=now, updated_at=now)


def branch_recent(branch_id, *, limit=20):
    return (
        _active_qs()
        .filter(branch_id=branch_id)
        .select_related("recipient", "created_by")
        .order_by("-created_at")[:limit]
    )


def expire_fee_notifications_for_invoice(invoice_id) -> int:
    """Expire open fee reminder notifications when invoice is paid."""
    now = timezone.now()
    return (
        Notification.objects.filter(
            related_entity_type="invoice",
            related_entity_id=invoice_id,
            notification_type__in=("fee.due_reminder", "fee.due_today", "fee.overdue"),
            is_active=True,
        )
        .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
        .update(expires_at=now, updated_at=now)
    )


def create_notification_row(**kwargs) -> Notification | None:
    """Insert row; return None on dedup conflict."""
    from django.db import IntegrityError, transaction

    try:
        with transaction.atomic():
            return Notification.objects.create(**kwargs)
    except IntegrityError:
        return None
