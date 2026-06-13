"""
HR — payroll processing. Money is integer paise (BigIntegerField); never float.

  - SalaryComponent   → reusable earning/deduction template for a branch (F-166)
  - PayrollRun        → a monthly payroll batch for a branch; immutable once locked (F-164)
  - Payslip           → computed payslip for one employee in one run
  - PayrollAdjustment → correction path for a locked run (F-164)
"""

from django.db import models

from apps.core.models import BaseModel
from apps.hr.enums import ComponentCalc, ComponentKind, PayrollRunStatus


class SalaryComponent(BaseModel):
    """Reusable earning/deduction template (F-166)."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="salary_components"
    )
    name = models.CharField(max_length=100)
    kind = models.CharField(max_length=10, choices=ComponentKind.choices)
    calc = models.CharField(max_length=20, choices=ComponentCalc.choices,
                            default=ComponentCalc.FIXED)
    amount_paise = models.BigIntegerField(default=0)
    percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)

    class Meta:
        db_table = "hr_salary_component"
        indexes = [models.Index(fields=["branch", "is_active"])]

    def __str__(self):
        return f"SalaryComponent({self.name})"


class PayrollRun(BaseModel):
    """A monthly payroll batch (F-158). Immutable once `locked_at` is set (F-164)."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="payroll_runs"
    )
    period_month = models.DateField(help_text="First day of the payroll month.")
    status = models.CharField(
        max_length=15, choices=PayrollRunStatus.choices,
        default=PayrollRunStatus.PENDING, db_index=True,
    )
    locked_at = models.DateTimeField(null=True, blank=True)
    executed_by = models.ForeignKey(
        "accounts.User", on_delete=models.SET_NULL, null=True, blank=True,
        related_name="payroll_runs_executed",
    )
    executed_at = models.DateTimeField(null=True, blank=True)
    totals = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True, default="")

    class Meta:
        db_table = "hr_payroll_run"
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "period_month"],
                condition=models.Q(is_active=True),
                name="unique_payroll_run_per_branch_month",
            ),
        ]

    @property
    def is_locked(self) -> bool:
        return self.locked_at is not None

    def __str__(self):
        return f"PayrollRun({self.branch_id}, {self.period_month})"


class Payslip(BaseModel):
    """Computed payslip for one employee in one run."""

    payroll_run = models.ForeignKey(
        PayrollRun, on_delete=models.CASCADE, related_name="payslips"
    )
    employee = models.ForeignKey(
        "hr.Employee", on_delete=models.PROTECT, related_name="payslips"
    )
    components = models.JSONField(default=list, blank=True)  # resolved earning/deduction lines
    gross_paise = models.BigIntegerField(default=0)
    deductions_paise = models.BigIntegerField(default=0)
    net_paise = models.BigIntegerField(default=0)
    worked_days = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    payable_days = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    pro_rated = models.BooleanField(default=False)
    pdf_key = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        db_table = "hr_payslip"
        constraints = [
            models.UniqueConstraint(
                fields=["payroll_run", "employee"],
                name="unique_payslip_per_run_employee",
            ),
        ]
        indexes = [models.Index(fields=["employee"])]

    def __str__(self):
        return f"Payslip({self.employee_id}, net={self.net_paise})"


class PayrollAdjustment(BaseModel):
    """A correction against a locked run, applied in a later run (F-164)."""

    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="payroll_adjustments"
    )
    employee = models.ForeignKey(
        "hr.Employee", on_delete=models.CASCADE, related_name="payroll_adjustments"
    )
    original_run = models.ForeignKey(
        PayrollRun, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="adjustments",
    )
    amount_paise = models.BigIntegerField(help_text="Signed; negative = recovery.")
    reason = models.TextField()
    applied_in_run = models.ForeignKey(
        PayrollRun, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="applied_adjustments",
    )

    class Meta:
        db_table = "hr_payroll_adjustment"

    def __str__(self):
        return f"PayrollAdjustment({self.employee_id}, {self.amount_paise})"
