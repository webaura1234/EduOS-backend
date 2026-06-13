"""HR query layer — all ORM lives in these modules."""

from apps.hr.queries import employee, leave, payroll

__all__ = ["employee", "leave", "payroll"]
