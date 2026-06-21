"""
Communications — notification preferences.

  - NotificationPreference → per-user channel opt-in/out (F-179). Phase-1 scope is the
    per-channel toggle the frontend uses; the full dispatch log lands with the
    Communications dispatch engine.
"""

from django.db import models

from apps.core.models import BaseModel


class NotificationPreference(BaseModel):
    """A user's notification channel preferences (F-179)."""

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="notification_preference"
    )
    in_app = models.BooleanField(default=True)
    sms = models.BooleanField(default=True)
    email = models.BooleanField(default=True)

    class Meta:
        db_table = "communications_notification_preference"
        verbose_name = "Notification Preference"

    def __str__(self):
        return f"NotificationPreference({self.user_id})"
