"""Grievance — a complaint/issue raised by a student or parent (F-255)."""

from django.db import models

from apps.core.models import BaseModel


class GrievanceStatus(models.TextChoices):
    OPEN = "open", "Open"
    IN_REVIEW = "in_review", "In review"
    RESOLVED = "resolved", "Resolved"
    CLOSED = "closed", "Closed"


class GrievanceRaiserRole(models.TextChoices):
    STUDENT = "student", "Student"
    PARENT = "parent", "Parent"


class Grievance(BaseModel):
    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="grievances",
    )
    # Who raised it, and which student it concerns (same user when a student self-raises).
    raised_by = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="raised_grievances",
    )
    raised_by_role = models.CharField(
        max_length=10, choices=GrievanceRaiserRole.choices, default=GrievanceRaiserRole.STUDENT,
    )
    student = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="grievances_about",
        limit_choices_to={"role": "student"},
    )

    category = models.CharField(max_length=100)
    subject = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=15, choices=GrievanceStatus.choices, default=GrievanceStatus.OPEN, db_index=True,
    )

    assigned_to = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="assigned_grievances",
    )
    assigned_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True, default="")

    class Meta:
        db_table = "grievances_grievance"
        indexes = [models.Index(fields=["branch", "status", "-created_at"])]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Grievance({self.subject}, {self.status})"
