"""Announcement — a broadcast notice to students/parents/staff (F-195)."""

from django.db import models

from apps.core.models import BaseModel


class AnnouncementTargetType(models.TextChoices):
    ALL = "all", "Everyone"
    BATCH = "batch", "Batch"
    DEPARTMENT = "department", "Department"
    ROLE = "role", "Role"


class AnnouncementScope(models.TextChoices):
    INSTITUTION = "institution", "Institution"
    BRANCH = "branch", "Branch"


class Announcement(BaseModel):
    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="announcements",
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")

    target_type = models.CharField(
        max_length=15, choices=AnnouncementTargetType.choices,
        default=AnnouncementTargetType.ALL,
    )
    # Holds the batch id / department id / role depending on target_type.
    target_value = models.CharField(max_length=100, blank=True, default="")
    target_label = models.CharField(max_length=150, blank=True, default="")

    scope = models.CharField(
        max_length=15, choices=AnnouncementScope.choices, default=AnnouncementScope.BRANCH,
    )
    # Subset of {in_app, sms, email}.
    channels = models.JSONField(default=list, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "communications_announcement"
        indexes = [models.Index(fields=["branch", "-created_at"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Announcement({self.title})"


class AnnouncementRead(BaseModel):
    """Marks an announcement as read by a specific user (per-user read state)."""

    announcement = models.ForeignKey(
        Announcement, on_delete=models.CASCADE, related_name="reads",
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="announcement_reads",
    )
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "communications_announcement_read"
        constraints = [
            models.UniqueConstraint(
                fields=["announcement", "user"], name="unique_announcement_read_per_user",
            ),
        ]
        indexes = [models.Index(fields=["user", "announcement"])]

    def __str__(self):
        return f"Read({self.announcement_id} by {self.user_id})"
