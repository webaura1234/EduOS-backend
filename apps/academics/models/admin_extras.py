"""Admin Academics screen domains: substitutions, study materials, calendar-change log."""

from django.db import models

from apps.core.models import BaseModel


class SubstitutionStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class AcademicSubstitution(BaseModel):
    """A substitute faculty covering a timetable slot on a specific date (F-295)."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="substitutions"
    )
    timetable_entry = models.ForeignKey(
        "academics.TimetableEntry", on_delete=models.CASCADE, related_name="substitutions"
    )
    original_faculty = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="substitutions_out",
    )
    substitute_faculty = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="substitutions_in",
    )
    date = models.DateField()
    reason = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=10, choices=SubstitutionStatus.choices, default=SubstitutionStatus.SCHEDULED,
    )

    class Meta:
        db_table = "academics_substitution"
        indexes = [models.Index(fields=["branch", "date"])]

    def __str__(self):
        return f"Substitution({self.timetable_entry_id} @ {self.date})"


class StudyMaterial(BaseModel):
    """A file attached to a timetable slot's session (F-179)."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="study_materials"
    )
    timetable_entry = models.ForeignKey(
        "academics.TimetableEntry", on_delete=models.CASCADE, related_name="study_materials"
    )
    session_date = models.DateField()
    file_name = models.CharField(max_length=255)
    s3_key = models.CharField(max_length=500, blank=True, default="")
    url = models.CharField(max_length=1000, blank=True, default="")
    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="uploaded_study_materials",
    )

    class Meta:
        db_table = "academics_study_material"
        indexes = [models.Index(fields=["branch", "timetable_entry"])]

    def __str__(self):
        return f"StudyMaterial({self.file_name})"


class CalendarChangeType(models.TextChoices):
    WORKING_DAYS = "working_days", "Working days"
    PERIOD = "period", "Period"
    HOLIDAY = "holiday", "Holiday"


class CalendarChange(BaseModel):
    """Audit log of calendar edits; drives the 'attendance frozen through' date."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="calendar_changes"
    )
    change_type = models.CharField(max_length=15, choices=CalendarChangeType.choices)
    description = models.TextField(blank=True, default="")
    effective_date = models.DateField()
    attendance_frozen_through = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "academics_calendar_change"
        indexes = [models.Index(fields=["branch", "-created_at"])]

    def __str__(self):
        return f"CalendarChange({self.change_type} @ {self.effective_date})"
