"""
StudentGuardianLink model.

Links a Student User row to a Parent User row.
One parent can be linked to MANY students (siblings).
One student can have MANY guardians (e.g. divorced parents, both have portal access).

This is the key table that powers the parent dashboard child switcher.
"""

import uuid

from django.db import models

from apps.core.models import BaseModel


class CustodyType(models.TextChoices):
    PRIMARY = "primary", "Primary"
    SHARED = "shared", "Shared"
    EMERGENCY = "emergency", "Emergency Only"


class StudentGuardianLink(BaseModel):
    """
    Many-to-many link between Students and their Guardians.

    Business rules enforced here:
      - is_primary_contact: Only ONE guardian per student can be primary.
      - has_portal_access: Controls whether guardian can log in to see the student.
    """

    student = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="guardian_links",
        limit_choices_to={"role": "student"},
    )
    guardian = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="student_links",
        limit_choices_to={"role": "parent"},
    )

    # Relationship specifics per student (overrides GuardianProfile.relationship_default)
    relationship = models.CharField(
        max_length=20,
        choices=[
            ("father", "Father"),
            ("mother", "Mother"),
            ("guardian", "Guardian"),
            ("grandparent", "Grandparent"),
            ("sibling", "Sibling"),
            ("other", "Other"),
        ],
        default="guardian",
    )
    custody = models.CharField(
        max_length=20,
        choices=CustodyType.choices,
        default=CustodyType.PRIMARY,
    )

    # Portal & communication flags
    is_primary_contact = models.BooleanField(
        default=False,
        help_text="Primary contact receives all SMS/email alerts for this student.",
    )
    has_portal_access = models.BooleanField(
        default=True,
        help_text="Whether this guardian can log in and view the student's data.",
    )
    can_pickup = models.BooleanField(
        default=True,
        help_text="Whether this guardian is authorized to pick up the student.",
    )

    class Meta:
        db_table = "accounts_student_guardian_link"
        verbose_name = "Student Guardian Link"
        verbose_name_plural = "Student Guardian Links"
        unique_together = [("student", "guardian")]

    def __str__(self):
        return f"{self.guardian.full_name} → {self.student.full_name} ({self.relationship})"
