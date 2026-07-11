"""Render notification title/message/action_url from templates."""

from rest_framework.exceptions import ValidationError

from apps.communications.enums import TYPE_TO_CATEGORY
from apps.communications.templates.action_urls import build_action_url
from apps.communications.templates.registry import TEMPLATES


def render_notification(notification_type: str, recipient, variables: dict) -> dict:
    """Return {category, title, message, priority, action_url} for create."""
    spec = TEMPLATES.get(notification_type)
    if not spec:
        raise ValidationError(f"Unknown notification type: {notification_type}")

    missing = spec["required"] - set(variables.keys())
    if missing:
        raise ValidationError(
            f"Missing template variables for {notification_type}: {sorted(missing)}"
        )

    title = spec["title"].format(**variables)
    message = spec["message"].format(**variables)
    action_url = build_action_url(
        notification_type,
        role=getattr(recipient, "role", ""),
        variables=variables,
    )
    if not action_url or action_url == "/":
        raise ValidationError(f"No action_url for {notification_type} / role {recipient.role}")

    return {
        "category": TYPE_TO_CATEGORY[notification_type],
        "title": title,
        "message": message,
        "priority": spec["priority"],
        "action_url": action_url,
    }
