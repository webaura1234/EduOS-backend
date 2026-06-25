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


class StudyMaterialFolder(BaseModel):
    """Admin-defined folder for organizing study materials within a class/batch."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="study_material_folders",
    )
    batch = models.ForeignKey(
        "academics.Batch", on_delete=models.CASCADE, related_name="study_material_folders",
    )
    name = models.CharField(max_length=100)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "academics_study_material_folder"
        constraints = [
            models.UniqueConstraint(
                fields=["batch", "name"],
                name="academics_study_material_folder_batch_name_uniq",
            ),
        ]
        indexes = [models.Index(fields=["branch", "batch"])]
        ordering = ["sort_order", "name"]

    def __str__(self):
        return f"StudyMaterialFolder({self.name})"


class StudyMaterial(BaseModel):
    """A study-material file attached to a class/batch (F-179). Admin-uploaded,
    visible to that class's students and its faculty."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="study_materials"
    )
    batch = models.ForeignKey(
        "academics.Batch", on_delete=models.CASCADE, related_name="study_materials",
    )
    folder = models.ForeignKey(
        StudyMaterialFolder, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="materials",
    )
    file_name = models.CharField(max_length=255)
    s3_key = models.CharField(max_length=500, blank=True, default="")
    url = models.CharField(max_length=1000, blank=True, default="")
    uploaded_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="uploaded_study_materials",
    )

    class Meta:
        db_table = "academics_study_material"
        indexes = [models.Index(fields=["branch", "batch"])]

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


class SyllabusUnit(BaseModel):
    """An orderable unit of a subject's syllabus (definition only — progress is per section)."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="syllabus_units"
    )
    subject = models.ForeignKey(
        "academics.Subject", on_delete=models.CASCADE, related_name="syllabus_units"
    )
    title = models.CharField(max_length=255)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = "academics_syllabus_unit"
        ordering = ["order", "created_at"]
        indexes = [models.Index(fields=["branch", "subject", "order"])]

    def __str__(self):
        return f"SyllabusUnit({self.title})"


class SyllabusUnitProgress(BaseModel):
    """Per class-section completion of a syllabus unit."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="syllabus_unit_progress",
    )
    batch = models.ForeignKey(
        "academics.Batch", on_delete=models.CASCADE, related_name="syllabus_unit_progress",
    )
    unit = models.ForeignKey(
        SyllabusUnit, on_delete=models.CASCADE, related_name="section_progress",
    )
    completed_at = models.DateTimeField()
    completed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="syllabus_unit_progress_marked",
    )

    class Meta:
        db_table = "academics_syllabus_unit_progress"
        constraints = [
            models.UniqueConstraint(fields=["batch", "unit"], name="academics_syllabus_progress_batch_unit_uniq"),
        ]
        indexes = [models.Index(fields=["branch", "batch"])]

    def __str__(self):
        return f"SyllabusUnitProgress({self.batch_id}, {self.unit_id})"
