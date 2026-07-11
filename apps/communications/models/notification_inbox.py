"""In-app notification inbox — one row per recipient per event."""

from django.db import models

from apps.communications.enums import NotificationCategory, NotificationPriority
from apps.core.models import BaseModel


class Notification(BaseModel):
    tenant = models.ForeignKey(
        "organizations.Tenant", on_delete=models.CASCADE, related_name="notifications",
    )
    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="notifications",
    )
    recipient = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="notifications",
    )
    category = models.CharField(max_length=20, choices=NotificationCategory.choices)
    notification_type = models.CharField(max_length=64, db_column="type")
    priority = models.CharField(
        max_length=10, choices=NotificationPriority.choices,
        default=NotificationPriority.NORMAL,
    )
    title = models.CharField(max_length=255)
    message = models.TextField()
    action_url = models.CharField(max_length=512)
    related_entity_type = models.CharField(max_length=64, blank=True, default="")
    related_entity_id = models.UUIDField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    dedup_key = models.CharField(max_length=255)

    class Meta:
        db_table = "communications_notification"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "recipient", "dedup_key"],
                name="unique_notification_dedup_per_recipient",
            ),
        ]
        indexes = [
            models.Index(fields=["recipient", "-created_at"]),
            models.Index(fields=["branch", "-created_at"]),
            models.Index(fields=["recipient", "read_at"]),
        ]

    def __str__(self):
        return f"Notification({self.notification_type} → {self.recipient_id})"
