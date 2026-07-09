from __future__ import annotations

from django.conf import settings
from django.db import models


class WalkthroughCompletion(models.Model):
    """
    Stores per-user walkthrough completion flags.

    We store arbitrary string keys so we can evolve tours without schema churn.
    Examples:
      - dashboard:super_admin
      - module:attendance:admin
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="walkthrough_completions",
        db_index=True,
    )
    key = models.CharField(max_length=120, db_index=True)
    completed_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "accounts_walkthrough_completion"
        constraints = [
            models.UniqueConstraint(fields=["user", "key"], name="unique_walkthrough_key_per_user"),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.key}"

