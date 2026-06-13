"""
HR — staff leave management (system of record for employee leave + balances).

  - LeaveBalance      → per-employee, per-type annual balance (accrual + decrement)
  - LeaveApplication  → an employee leave request with approval workflow + COI routing
"""

from django.db import models

from apps.core.models import BaseModel
from apps.hr.enums import LeaveStatus, LeaveType


class LeaveBalance(BaseModel):
    """Per-employee, per-type leave balance for a year (F-157)."""

    employee = models.ForeignKey(
        "hr.Employee", on_delete=models.CASCADE, related_name="leave_balances"
    )
    leave_type = models.CharField(max_length=10, choices=LeaveType.choices)
    year = models.CharField(max_length=10, help_text='Financial year label, e.g. "2024-25".')
    balance_days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    accrual_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = "hr_leave_balance"
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "leave_type", "year"],
                name="unique_balance_per_employee_type_year",
            ),
        ]

    def __str__(self):
        return f"LeaveBalance({self.employee_id}, {self.leave_type}, {self.balance_days})"


class LeaveApplication(BaseModel):
    """An employee leave request with approve/reject workflow (F-157/F-162/F-163)."""

    employee = models.ForeignKey(
        "hr.Employee", on_delete=models.CASCADE, related_name="leave_applications"
    )
    leave_type = models.CharField(max_length=10, choices=LeaveType.choices)
    from_date = models.DateField()
    to_date = models.DateField()
    days = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    reason = models.TextField(blank=True, default="")

    status = models.CharField(
        max_length=10, choices=LeaveStatus.choices, default=LeaveStatus.PENDING, db_index=True
    )
    approver = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="hr_leaves_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    decision_note = models.TextField(blank=True, default="")
    # EC-GUARD-03 analog: routed to admin/super_admin because approver == applicant.
    auto_routed_coi = models.BooleanField(default=False)

    class Meta:
        db_table = "hr_leave_application"
        indexes = [models.Index(fields=["employee", "status"])]

    def __str__(self):
        return f"LeaveApplication({self.employee_id}, {self.from_date}→{self.to_date})"
