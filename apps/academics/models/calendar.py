"""
Branch calendar — academic years, terms/semesters, and holidays.
"""

from django.db import models

from apps.core.models import BaseModel


class PeriodType(models.TextChoices):
    TERM = "term", "Term"
    SEMESTER = "semester", "Semester"


class AcademicYear(BaseModel):
    """
    Branch-scoped school/college year (e.g. 2024-25).
    Only one per branch may be current; frozen years block structural edits.
    """

    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="academic_years",
    )
    name = models.CharField(max_length=20, help_text='e.g. "2024-25"')
    start_date = models.DateField()
    end_date = models.DateField()
    is_current = models.BooleanField(default=False, db_index=True)
    is_frozen = models.BooleanField(
        default=False,
        help_text="Once frozen, no structural changes are allowed.",
    )

    class Meta:
        db_table = "academics_academic_year"
        verbose_name = "Academic Year"
        verbose_name_plural = "Academic Years"
        unique_together = [("branch", "name")]
        constraints = [
            models.UniqueConstraint(
                fields=["branch"],
                condition=models.Q(is_current=True),
                name="unique_current_academic_year_per_branch",
            )
        ]

    def __str__(self):
        return f"{self.branch} — {self.name}"


class AcademicPeriod(BaseModel):
    """Term (school) or semester (college) within an academic year."""

    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="periods",
    )
    period_type = models.CharField(max_length=10, choices=PeriodType.choices)
    sequence = models.PositiveSmallIntegerField(
        help_text="1 = first term/semester of the year.",
    )
    name = models.CharField(max_length=50, help_text='e.g. "Term 1"')
    start_date = models.DateField()
    end_date = models.DateField()

    class Meta:
        db_table = "academics_academic_period"
        verbose_name = "Academic Period"
        verbose_name_plural = "Academic Periods"
        unique_together = [("academic_year", "sequence")]
        ordering = ["sequence"]

    def __str__(self):
        return f"{self.academic_year.name} — {self.name}"


class HolidayType(models.TextChoices):
    PUBLIC = "public", "Public Holiday"
    SCHOOL = "school", "School Holiday"
    EXAM = "exam", "Exam Day"
    OPTIONAL = "optional", "Optional Holiday"


class Holiday(BaseModel):
    """Branch-level holiday; applies_to is a JSON role/all config."""

    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="holidays",
    )
    date = models.DateField(db_index=True)
    name = models.CharField(max_length=150)
    holiday_type = models.CharField(
        max_length=20,
        choices=HolidayType.choices,
        default=HolidayType.PUBLIC,
    )
    applies_to = models.JSONField(
        default=dict,
        help_text='e.g. {"all": true} or {"roles": ["student", "faculty"]}',
    )

    class Meta:
        db_table = "academics_holiday"
        verbose_name = "Holiday"
        verbose_name_plural = "Holidays"
        unique_together = [("branch", "date")]

    def __str__(self):
        return f"{self.branch.name} — {self.name} ({self.date})"
