"""HR & Payroll enums."""

from django.db import models


class EmploymentType(models.TextChoices):
    FULL_TIME = "full_time", "Full Time"
    PART_TIME = "part_time", "Part Time"
    CONTRACT = "contract", "Contract"
    VISITING = "visiting", "Visiting"


class LeaveType(models.TextChoices):
    CASUAL = "casual", "Casual"
    SICK = "sick", "Sick"
    EARNED = "earned", "Earned"
    UNPAID = "unpaid", "Unpaid"


class LeaveStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    CANCELLED = "cancelled", "Cancelled"


class PayrollRunStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RUNNING = "running", "Running"
    SUCCEEDED = "succeeded", "Succeeded"
    FAILED = "failed", "Failed"
    LOCKED = "locked", "Locked"


class ComponentKind(models.TextChoices):
    EARNING = "earning", "Earning"
    DEDUCTION = "deduction", "Deduction"


class ComponentCalc(models.TextChoices):
    FIXED = "fixed", "Fixed amount"
    PERCENT_OF_BASIC = "percent_of_basic", "Percent of basic"
