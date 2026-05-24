"""
Curriculum and teaching assignments — subjects, batch offerings, faculty.
"""

from django.db import models

from apps.core.models import BaseModel

from .calendar import AcademicPeriod
from .structure import Batch, Course


class SubjectType(models.TextChoices):
    THEORY = "theory", "Theory"
    PRACTICAL = "practical", "Practical"
    PROJECT = "project", "Project"
    ELECTIVE = "elective", "Elective"


class Subject(BaseModel):
    """Subject / paper defined on a course curriculum."""

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="subjects",
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, blank=True, default="")
    subject_type = models.CharField(
        max_length=15,
        choices=SubjectType.choices,
        default=SubjectType.THEORY,
    )
    max_marks = models.PositiveSmallIntegerField(default=100)
    pass_marks = models.PositiveSmallIntegerField(default=35)
    credits = models.PositiveSmallIntegerField(null=True, blank=True)
    is_elective = models.BooleanField(default=False)

    class Meta:
        db_table = "academics_subject"
        verbose_name = "Subject"
        verbose_name_plural = "Subjects"
        unique_together = [("course", "code")]

    def __str__(self):
        return f"{self.course.name} — {self.name}"


class BatchSubject(BaseModel):
    """Which subject is taught in which batch during which academic period."""

    batch = models.ForeignKey(
        Batch,
        on_delete=models.CASCADE,
        related_name="batch_subjects",
    )
    subject = models.ForeignKey(
        Subject,
        on_delete=models.CASCADE,
        related_name="batch_subjects",
    )
    academic_period = models.ForeignKey(
        AcademicPeriod,
        on_delete=models.CASCADE,
        related_name="batch_subjects",
    )
    is_required = models.BooleanField(default=True)

    class Meta:
        db_table = "academics_batch_subject"
        verbose_name = "Batch Subject"
        verbose_name_plural = "Batch Subjects"
        unique_together = [("batch", "subject", "academic_period")]

    def __str__(self):
        return f"{self.batch} — {self.subject.name} ({self.academic_period.name})"


class BatchFacultyRole(models.TextChoices):
    PRIMARY = "primary", "Primary"
    SUBSTITUTE = "substitute", "Substitute"
    CO_TEACHER = "co_teacher", "Co-Teacher"


class BatchFaculty(BaseModel):
    """Standing faculty assignment for a batch-subject (see TimetableEntry for weekly slots)."""

    batch_subject = models.ForeignKey(
        BatchSubject,
        on_delete=models.CASCADE,
        related_name="faculty_assignments",
    )
    faculty = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="batch_faculty_assignments",
        limit_choices_to={"role": "faculty"},
    )
    role = models.CharField(
        max_length=15,
        choices=BatchFacultyRole.choices,
        default=BatchFacultyRole.PRIMARY,
    )
    assigned_at = models.DateField()
    ended_at = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "academics_batch_faculty"
        verbose_name = "Batch Faculty"
        verbose_name_plural = "Batch Faculty"

    def __str__(self):
        return f"{self.faculty.full_name} — {self.batch_subject} ({self.role})"
