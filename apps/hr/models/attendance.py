"""Staff (teacher) daily attendance — self check-in, used for monthly present-days."""

from django.db import models

from apps.core.models import BaseModel


class StaffAttendanceStatus(models.TextChoices):
    PRESENT = "present", "Present"
    ABSENT = "absent", "Absent"
    LEAVE = "leave", "Leave"


class StaffAttendance(BaseModel):
    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="staff_attendance",
    )
    user = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="staff_attendance",
    )
    date = models.DateField(db_index=True)
    status = models.CharField(
        max_length=10, choices=StaffAttendanceStatus.choices,
        default=StaffAttendanceStatus.PRESENT,
    )
    marked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "hr_staff_attendance"
        constraints = [
            models.UniqueConstraint(fields=["user", "date"], name="unique_staff_attendance_per_day"),
        ]
        indexes = [models.Index(fields=["user", "date"])]

    def __str__(self):
        return f"StaffAttendance({self.user_id} {self.date} {self.status})"
