"""Create in-app notifications — dedup, preference gate, template render."""

from datetime import date

from apps.communications.queries import notification as pref_q
from apps.communications.queries import inbox as inbox_q
from apps.communications.templates.expiry import compute_expires_at
from apps.communications.templates.render import render_notification


def _in_app_enabled(user) -> bool:
    pref = pref_q.get_or_create_preference(user)
    return pref.in_app


def create_notification(
    notification_type: str,
    *,
    tenant,
    branch,
    recipient,
    variables: dict,
    dedup_key: str,
    created_by=None,
    related_entity_type: str = "",
    related_entity_id=None,
    due_date: date | None = None,
) -> object | None:
    """Render template and persist notification. Returns None if skipped/deduped."""
    if not _in_app_enabled(recipient):
        return None

    rendered = render_notification(notification_type, recipient, variables)
    expires_at = compute_expires_at(
        notification_type, due_date=due_date,
    )

    return inbox_q.create_notification_row(
        tenant=tenant,
        branch=branch,
        recipient=recipient,
        category=rendered["category"],
        notification_type=notification_type,
        priority=rendered["priority"],
        title=rendered["title"],
        message=rendered["message"],
        action_url=rendered["action_url"],
        related_entity_type=related_entity_type,
        related_entity_id=related_entity_id,
        created_by=created_by,
        updated_by=created_by,
        expires_at=expires_at,
        dedup_key=dedup_key,
    )
