"""Examinations — exam setup and scheduling."""

from django.core.validators import MinValueValidator
from django.db import models

from apps.core.models import BaseModel
from apps.examinations.enums import ExamType, ResultStatus


class GradeScale(BaseModel):
    """
    Grading scheme (marks → grade/GPA mapping) for a course.

    F-128/F-050 (college), F-131 (school). Per-course scale with optional branch default.
    """

    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="grade_scales",
    )
    course = models.ForeignKey(
        "academics.Course",
        on_delete=models.CASCADE,
        related_name="grade_scales",
    )
    name = models.CharField(max_length=100)
    bands = models.JSONField(
        default=list,
        help_text='[{min_percent, max_percent, grade, grade_point}]',
    )
    grace_marks_max = models.PositiveSmallIntegerField(
        default=0,
        help_text="College-only grace marks cap (F-050/F-128).",
    )
    is_default = models.BooleanField(
        default=False,
        help_text="Branch fallback when no course-specific scale exists.",
    )

    class Meta:
        db_table = "examinations_grade_scale"
        verbose_name = "Grade Scale"
        verbose_name_plural = "Grade Scales"
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "course", "name"],
                name="unique_grade_scale_name_per_course",
            ),
        ]

    def __str__(self):
        return f"{self.branch_id} — {self.name}"


class Exam(BaseModel):
    """
    An exam event (e.g. Mid-Term, Final) for an academic period.

    F-116 — groups schedule slots, registrations, marks, and results.
    """

    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="exams",
    )
    academic_period = models.ForeignKey(
        "academics.AcademicPeriod",
        on_delete=models.CASCADE,
        related_name="exams",
    )
    name = models.CharField(max_length=150)
    exam_type = models.CharField(max_length=15, choices=ExamType.choices, default=ExamType.INTERNAL)
    exam_fee_paise = models.BigIntegerField(
        default=0,
        help_text="Flat exam fee charged on registration (Stage 3 fees integration).",
    )
    marks_deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Faculty marks submission deadline (EC-FORM-05).",
    )
    is_published = models.BooleanField(
        default=False,
        help_text="Denormalized convenience — true when results are published.",
    )
    result_status = models.CharField(
        max_length=15,
        choices=ResultStatus.choices,
        default=ResultStatus.PROVISIONAL,
    )
    publish_in_progress = models.BooleanField(
        default=False,
        help_text="Set during two-step publish to block concurrent publishers (EC-CONCUR-01).",
    )

    class Meta:
        db_table = "examinations_exam"
        verbose_name = "Exam"
        verbose_name_plural = "Exams"
        indexes = [
            models.Index(fields=["branch", "academic_period", "exam_type"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.exam_type})"


class ExamScheduleSlot(BaseModel):
    """
    Per-subject date/time/room slot within an Exam.

    F-116/F-134 — clash detection on overlapping (room, [start, end]).
    """

    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="schedule_slots",
    )
    subject = models.ForeignKey(
        "academics.Subject",
        on_delete=models.PROTECT,
        related_name="exam_schedule_slots",
    )
    batch = models.ForeignKey(
        "academics.Batch",
        on_delete=models.CASCADE,
        related_name="exam_schedule_slots",
    )
    room = models.ForeignKey(
        "academics.Room",
        on_delete=models.PROTECT,
        related_name="exam_schedule_slots",
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()
    max_capacity = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Override room capacity for this slot; defaults to room.capacity.",
    )
    max_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        help_text="Snapshot from subject; overridable per slot.",
    )
    required_invigilators = models.PositiveSmallIntegerField(
        default=1,
        validators=[MinValueValidator(1)],
        help_text="Number of faculty required to invigilate this slot.",
    )
    seating_session = models.ForeignKey(
        "ExamSeatingSession",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="schedule_slots",
    )

    class Meta:
        db_table = "examinations_exam_schedule_slot"
        verbose_name = "Exam Schedule Slot"
        verbose_name_plural = "Exam Schedule Slots"
        indexes = [
            models.Index(fields=["room", "start_at", "end_at"]),
            models.Index(fields=["exam", "batch"]),
        ]

    def __str__(self):
        return f"{self.exam_id} — {self.subject_id} @ {self.start_at:%Y-%m-%d %H:%M}"


class ExamSeatingSession(BaseModel):
    """Shared hall seating across multiple schedule slots (school combined exams)."""

    exam = models.ForeignKey(
        Exam,
        on_delete=models.CASCADE,
        related_name="seating_sessions",
    )
    name = models.CharField(max_length=150)
    hall_room = models.ForeignKey(
        "academics.Room",
        on_delete=models.PROTECT,
        related_name="exam_seating_sessions",
    )
    start_at = models.DateTimeField()
    end_at = models.DateTimeField()

    class Meta:
        db_table = "examinations_exam_seating_session"
        verbose_name = "Exam Seating Session"
        verbose_name_plural = "Exam Seating Sessions"

    def __str__(self):
        return f"{self.name} @ {self.start_at:%Y-%m-%d %H:%M}"


class InvigilatorDuty(BaseModel):
    """Faculty assigned to invigilate an exam schedule slot (F-119)."""

    schedule_slot = models.ForeignKey(
        ExamScheduleSlot,
        on_delete=models.CASCADE,
        related_name="invigilator_duties",
    )
    faculty = models.ForeignKey(
        "accounts.User",
        on_delete=models.CASCADE,
        related_name="invigilator_duties",
        limit_choices_to={"role": "faculty"},
    )

    class Meta:
        db_table = "examinations_invigilator_duty"
        verbose_name = "Invigilator Duty"
        verbose_name_plural = "Invigilator Duties"
        constraints = [
            models.UniqueConstraint(
                fields=["schedule_slot", "faculty"],
                name="unique_invigilator_per_slot",
            ),
        ]

    def __str__(self):
        return f"{self.schedule_slot_id} — {self.faculty_id}"
