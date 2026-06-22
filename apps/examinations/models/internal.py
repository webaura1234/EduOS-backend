"""InternalMark — continuous/internal assessment score for a student in a subject (F-253)."""

from django.db import models

from apps.core.models import BaseModel


class InternalMark(BaseModel):
    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="internal_marks",
    )
    student_profile = models.ForeignKey(
        "accounts.StudentProfile", on_delete=models.CASCADE, related_name="internal_marks",
    )
    subject = models.ForeignKey(
        "academics.Subject", on_delete=models.CASCADE, related_name="internal_marks",
    )
    marks = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Null = not yet entered / absent.",
    )
    max_marks = models.PositiveSmallIntegerField(default=100)
    # F-253: entry blocked past this datetime unless an admin overrides.
    hard_deadline_at = models.DateTimeField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="recorded_internal_marks",
    )

    class Meta:
        db_table = "examinations_internal_mark"
        constraints = [
            models.UniqueConstraint(
                fields=["student_profile", "subject"],
                condition=models.Q(is_active=True),
                name="unique_internal_mark_per_student_subject",
            ),
        ]
        indexes = [models.Index(fields=["branch", "subject"])]

    def __str__(self):
        return f"InternalMark({self.student_profile_id}, {self.subject_id}, {self.marks})"
