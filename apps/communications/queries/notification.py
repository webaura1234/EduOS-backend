"""Queries — NotificationPreference (all ORM here)."""

from apps.communications.models import NotificationPreference


def get_or_create_preference(user) -> NotificationPreference:
    pref, _ = NotificationPreference.objects.get_or_create(
        user=user, defaults={"created_by": user, "updated_by": user}
    )
    return pref


def update_preference(pref: NotificationPreference, fields: dict, user=None) -> NotificationPreference:
    allowed = {k: v for k, v in fields.items() if k in {"in_app", "sms", "email"}}
    for k, v in allowed.items():
        setattr(pref, k, v)
    if user:
        pref.updated_by = user
    if allowed:
        pref.save(update_fields=list(allowed.keys()) + (["updated_by"] if user else []) + ["updated_at"])
    return pref
