"""
Timetable models — period slots, rooms, and weekly schedule entries.

Attendance sessions reference period slots (slot_id). Faculty and room
clash detection is enforced on TimetableEntry uniqueness per branch schedule.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from apps.core.models import BaseModel


class DayOfWeek(models.IntegerChoices):
    MONDAY = 1, "Monday"
    TUESDAY = 2, "Tuesday"
    WEDNESDAY = 3, "Wednesday"
    THURSDAY = 4, "Thursday"
    FRIDAY = 5, "Friday"
    SATURDAY = 6, "Saturday"
    SUNDAY = 7, "Sunday"


class TimetableEntryStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    TBD = "tbd", "TBD"  # Subject/faculty removed — admin must reassign


class PeriodSlot(BaseModel):
    """
    A named period in the school day (e.g. Period 1, 09:00–09:45).

    Scoped to a Branch. Referenced by TimetableEntry and AttendanceSession.
    """

    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="period_slots",
    )
    name = models.CharField(max_length=50, help_text='e.g. "Period 1", "Assembly"')
    sequence = models.PositiveSmallIntegerField(
        help_text="Order within the day (1 = first period).",
    )
    start_time = models.TimeField()
    end_time = models.TimeField()

    class Meta:
        db_table = "academics_period_slot"
        verbose_name = "Period Slot"
        verbose_name_plural = "Period Slots"
        unique_together = [("branch", "sequence")]
        ordering = ["sequence"]

    def __str__(self):
        return f"{self.branch.name} — {self.name} ({self.start_time:%H:%M})"


class Room(BaseModel):
    """Physical room or lab used for timetable and exam scheduling."""

    branch = models.ForeignKey(
        "organizations.Branch",
        on_delete=models.CASCADE,
        related_name="rooms",
    )
    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, blank=True, default="")
    capacity = models.PositiveSmallIntegerField(default=40)
    is_lab = models.BooleanField(default=False)

    class Meta:
        db_table = "academics_room"
        verbose_name = "Room"
        verbose_name_plural = "Rooms"
        unique_together = [("branch", "name")]

    def __str__(self):
        return f"{self.branch.name} — {self.name}"


class Timetable(BaseModel):
    """
    Published weekly timetable for a Batch in an AcademicPeriod.

    Entries hang off this header so admins can version or draft schedules.
    """

    batch = models.ForeignKey(
        "academics.Batch",
        on_delete=models.CASCADE,
        related_name="timetables",
    )
    academic_period = models.ForeignKey(
        "academics.AcademicPeriod",
        on_delete=models.CASCADE,
        related_name="timetables",
    )
    name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text='Optional label, e.g. "Term 1 — Final".',
    )
    is_published = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = "academics_timetable"
        verbose_name = "Timetable"
        verbose_name_plural = "Timetables"
        unique_together = [("batch", "academic_period")]

    def __str__(self):
        label = self.name or f"{self.batch} — {self.academic_period.name}"
        return label


class TimetableEntry(BaseModel):
    """
    One cell in the weekly grid: batch-subject taught at a period on a weekday.

    Faculty and room are optional until assigned. Status TBD when subject/faculty
    is removed (EC-TT-05 / EC-TT-06).
    """

    timetable = models.ForeignKey(
        Timetable,
        on_delete=models.CASCADE,
        related_name="entries",
    )
    batch_subject = models.ForeignKey(
        "academics.BatchSubject",
        on_delete=models.CASCADE,
        related_name="timetable_entries",
    )
    period_slot = models.ForeignKey(
        PeriodSlot,
        on_delete=models.PROTECT,
        related_name="timetable_entries",
    )
    day_of_week = models.PositiveSmallIntegerField(
        choices=DayOfWeek.choices,
        validators=[MinValueValidator(1), MaxValueValidator(7)],
    )
    faculty = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timetable_entries",
        limit_choices_to={"role": "faculty"},
    )
    room = models.ForeignKey(
        Room,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="timetable_entries",
    )
    status = models.CharField(
        max_length=10,
        choices=TimetableEntryStatus.choices,
        default=TimetableEntryStatus.ACTIVE,
        db_index=True,
    )

    class Meta:
        db_table = "academics_timetable_entry"
        verbose_name = "Timetable Entry"
        verbose_name_plural = "Timetable Entries"
        unique_together = [("timetable", "batch_subject", "day_of_week", "period_slot")]
        constraints = [
            models.UniqueConstraint(
                fields=["faculty", "day_of_week", "period_slot"],
                condition=models.Q(
                    faculty__isnull=False,
                    status=TimetableEntryStatus.ACTIVE,
                ),
                name="unique_faculty_slot_per_day",
            ),
            models.UniqueConstraint(
                fields=["room", "day_of_week", "period_slot"],
                condition=models.Q(
                    room__isnull=False,
                    status=TimetableEntryStatus.ACTIVE,
                ),
                name="unique_room_slot_per_day",
            ),
        ]

    def __str__(self):
        return (
            f"{self.batch_subject} — {self.get_day_of_week_display()} "
            f"{self.period_slot.name}"
        )
