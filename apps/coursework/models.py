"""Coursework — homework (and, later, notes) authored by faculty for a class."""

from django.db import models

from apps.core.models import BaseModel


class HomeworkStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PUBLISHED = "published", "Published"


class Homework(BaseModel):
    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="homework",
    )
    batch = models.ForeignKey(
        "academics.Batch", on_delete=models.CASCADE, related_name="homework",
    )
    date = models.DateField()
    title = models.CharField(max_length=255)
    details = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=15, choices=HomeworkStatus.choices, default=HomeworkStatus.DRAFT, db_index=True,
    )
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "coursework_homework"
        indexes = [models.Index(fields=["branch", "batch", "-date"])]
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"Homework({self.title}, {self.date})"
