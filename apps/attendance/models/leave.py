"""LeaveRequest — student or staff leave application."""

from django.db import models

from apps.attendance.enums import LeaveApplicantRole, LeaveStatus
from apps.core.models import BaseModel


class LeaveRequest(BaseModel):
    """A leave application covering a date range; approval drives attendance status."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="leave_requests"
    )
    applicant_role = models.CharField(max_length=10, choices=LeaveApplicantRole.choices)

    student = models.ForeignKey(
        "admissions.StudentEnrollment", on_delete=models.CASCADE, null=True, blank=True,
        related_name="leave_requests",
    )
    employee = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, null=True, blank=True,
        related_name="staff_leave_requests",
    )
    applied_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, related_name="submitted_leaves",
        help_text="Who submitted (student self, parent, faculty, or staff).",
    )

    from_date = models.DateField()
    to_date = models.DateField()
    reason = models.TextField(blank=True, default="")

    status = models.CharField(max_length=10, choices=LeaveStatus.choices, default=LeaveStatus.PENDING)
    approver = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_leaves"
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True, default="")

    class Meta:
        db_table = "attendance_leave_request"
        verbose_name = "Leave Request"
        verbose_name_plural = "Leave Requests"
        indexes = [
            models.Index(fields=["branch", "status"]),
            models.Index(fields=["student", "from_date"]),
        ]

    def __str__(self):
        who = self.student_id or self.employee_id
        return f"Leave {who} {self.from_date}→{self.to_date} ({self.status})"
