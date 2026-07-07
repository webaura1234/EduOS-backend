"""Gallery enums."""

from django.db import models


class AlbumVisibility(models.TextChoices):
    STUDENTS = "students", "Students"
    PARENTS = "parents", "Parents"
    FACULTY = "faculty", "Faculty"
    STAFF_ONLY = "staff_only", "Staff only"
    PRIVATE = "private", "Private"


class ProcessingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"
