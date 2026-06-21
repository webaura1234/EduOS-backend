"""
Academic hierarchy — department → course → batch (section).
"""

from django.db import models

from apps.core.models import BaseModel

from .calendar import AcademicYear


class DepartmentType(models.TextChoices):
    STREAM = "stream", "Stream"
    DEPARTMENT = "department", "Department"


class Department(BaseModel):
    """School stream or college department, scoped to a branch."""

    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="departments",
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, blank=True, default="")
    department_type = models.CharField(
        max_length=15,
        choices=DepartmentType.choices,
        default=DepartmentType.DEPARTMENT,
    )
    head_faculty = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="headed_departments",
        limit_choices_to={"role": "faculty"},
    )
    # Optional nesting: a sub-department points to its parent (null = top-level).
    parent = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="children",
    )

    class Meta:
        db_table = "academics_department"
        verbose_name = "Department"
        verbose_name_plural = "Departments"
        unique_together = [("branch", "name")]

    def __str__(self):
        return f"{self.branch.name} — {self.name}"


class Course(BaseModel):
    """School class (grade) or college degree program."""

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name="courses",
    )
    name = models.CharField(max_length=150)
    code = models.CharField(max_length=20, blank=True, default="")
    duration_years = models.PositiveSmallIntegerField(default=1)
    regulation = models.CharField(max_length=20, blank=True, default="")
    total_credits = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        db_table = "academics_course"
        verbose_name = "Course"
        verbose_name_plural = "Courses"
        unique_together = [("department", "name")]

    def __str__(self):
        return f"{self.department.name} — {self.name}"


class Batch(BaseModel):
    """School section or college batch — students in a course for one academic year."""

    course = models.ForeignKey(
        Course,
        on_delete=models.CASCADE,
        related_name="batches",
    )
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="batches",
    )
    name = models.CharField(max_length=50, help_text='e.g. "Section A"')
    capacity = models.PositiveSmallIntegerField(default=40)
    class_teacher = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="class_teacher_batches",
        limit_choices_to={"role": "faculty"},
    )

    class Meta:
        db_table = "academics_batch"
        verbose_name = "Batch"
        verbose_name_plural = "Batches"
        unique_together = [("course", "academic_year", "name")]

    def __str__(self):
        return f"{self.course.name} — {self.name} ({self.academic_year.name})"
