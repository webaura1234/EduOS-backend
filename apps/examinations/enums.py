"""Enumerations for the examinations app."""

from django.db import models


class ExamType(models.TextChoices):
    UNIT = "unit", "Unit Test"
    MIDTERM = "midterm", "Midterm"
    FINAL = "final", "Final"
    INTERNAL = "internal", "Internal"
    PRACTICAL = "practical", "Practical"
    ARREAR = "arrear", "Arrear"


class MarksStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    LOCKED = "locked", "Locked"


class ResultStatus(models.TextChoices):
    PROVISIONAL = "provisional", "Provisional"
    PUBLISHED = "published", "Published"
    REVISED = "revised", "Revised"


class AssignmentStatus(models.TextChoices):
    OPEN = "open", "Open"
    CLOSED = "closed", "Closed"


class SubmissionStatus(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    LATE = "late", "Late"
    GRADED = "graded", "Graded"


class MarksAuditType(models.TextChoices):
    LATE_SUBMIT_OVERRIDE = "late_submit_override", "Late submit override"
    CONFLICT_OVERRIDE = "conflict_override", "Conflict-of-interest override"
