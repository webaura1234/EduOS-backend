"""Examinations — assignments and homework."""

from django.db import models

from apps.core.models import BaseModel
from apps.examinations.enums import AssignmentStatus, SubmissionStatus


class Assignment(BaseModel):
    """
    Coursework task set by faculty for a batch-subject (F-126/F-219).

    Due date, max marks, submission tracking.
    """

    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    batch_subject = models.ForeignKey(
        "academics.BatchSubject",
        on_delete=models.CASCADE,
        related_name="assignments",
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    max_marks = models.DecimalField(max_digits=6, decimal_places=2)
    due_at = models.DateTimeField()
    status = models.CharField(
        max_length=10,
        choices=AssignmentStatus.choices,
        default=AssignmentStatus.OPEN,
    )
    created_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="created_assignments",
        limit_choices_to={"role": "faculty"},
    )

    class Meta:
        db_table = "examinations_assignment"
        verbose_name = "Assignment"
        verbose_name_plural = "Assignments"
        indexes = [
            models.Index(fields=["branch", "batch_subject", "status"]),
        ]

    def __str__(self):
        return self.title


class AssignmentSubmission(BaseModel):
    """
    Student submission for an assignment (F-126/F-219).

    plagiarism_score is an indicator only — not a hard block.

    # ENROLLMENT SEAM — student FK migrates to StudentEnrollment in Stage 5.
    """

    assignment = models.ForeignKey(
        Assignment,
        on_delete=models.CASCADE,
        related_name="submissions",
    )
    student = models.ForeignKey(
        "admissions.StudentEnrollment",
        on_delete=models.CASCADE,
        related_name="assignment_submissions",
    )
    file_key = models.CharField(max_length=512, blank=True, default="")
    plagiarism_score = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Similarity indicator only (F-126).",
    )
    graded_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
    )
    submission_status = models.CharField(
        max_length=15,
        choices=SubmissionStatus.choices,
        default=SubmissionStatus.SUBMITTED,
    )

    class Meta:
        db_table = "examinations_assignment_submission"
        verbose_name = "Assignment Submission"
        verbose_name_plural = "Assignment Submissions"
        constraints = [
            models.UniqueConstraint(
                fields=["assignment", "student"],
                name="unique_submission_per_assignment_student",
            ),
        ]

    def __str__(self):
        return f"{self.assignment_id} — {self.student_id}"
