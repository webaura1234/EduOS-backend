"""Gallery enums."""

from django.db import models


class AlbumVisibility(models.TextChoices):
    """Legacy single-value choices retained for migration / docs.

    Runtime albums store a JSON list of audiences (students, parents, faculty).
    Empty list = private. Prefer apps.gallery.services.visibility helpers.
    """

    STUDENTS = "students", "Students"
    PARENTS = "parents", "Parents"
    FACULTY = "faculty", "Faculty"
    STAFF_ONLY = "staff_only", "Staff only"
    PRIVATE = "private", "Private"


class ProcessingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"
