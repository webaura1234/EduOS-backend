import uuid

from django.conf import settings
from django.db import models


class BaseModel(models.Model):
    """
    Abstract base model that all other models in EduOS inherit from.
    Provides UUIDs, timestamps, soft-deletes, and audit trails.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Soft deletion
    is_active = models.BooleanField(default=True, db_index=True)

    # Audit trail
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_created",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_updated",
    )

    # Optimistic concurrency control
    version = models.IntegerField(default=1)

    class Meta:
        abstract = True

    def soft_delete(self, user=None):
        """Soft deletes the record instead of hard deleting."""
        self.is_active = False
        if user:
            self.updated_by = user
        self.save(update_fields=["is_active", "updated_by", "updated_at"])
