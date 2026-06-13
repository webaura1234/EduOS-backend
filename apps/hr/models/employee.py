"""
HR — employee records.

  - Employee      → HR master for a staff member (any role: faculty/admin/support),
                    linked 1:1 to accounts.User. Holds payroll/bank/document attributes.
  - BranchFaculty → multi-branch assignment with exactly one salary branch per faculty.
"""

from django.db import models

from apps.core.models import BaseModel
from apps.hr.enums import EmploymentType


class Employee(BaseModel):
    """HR master record for a staff member (F-156). employee_code is the HR identifier;
    for faculty it mirrors User.custom_login_id (the Employee ID they log in with)."""

    user = models.OneToOneField(
        "accounts.User", on_delete=models.CASCADE, related_name="employee"
    )
    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="employees"
    )
    employee_code = models.CharField(max_length=50)
    employment_type = models.CharField(
        max_length=15, choices=EmploymentType.choices, default=EmploymentType.FULL_TIME
    )
    designation = models.CharField(max_length=150, blank=True, default="")
    joined_at = models.DateField()
    exited_at = models.DateField(null=True, blank=True)

    # Salary structure snapshot: [{"name","kind","calc","amountPaise"|"percent"}].
    base_components = models.JSONField(default=list, blank=True)

    # Bank details (PII). F-281: a single accessor seam — encryption swapped in later.
    bank_account = models.CharField(max_length=64, blank=True, default="")
    ifsc = models.CharField(max_length=20, blank=True, default="")
    pan = models.CharField(max_length=20, blank=True, default="")

    document_keys = models.JSONField(default=list, blank=True)  # F-170 (S3 keys, stubbed)

    class Meta:
        db_table = "hr_employee"
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "employee_code"],
                condition=models.Q(is_active=True),
                name="unique_employee_code_per_branch",
            ),
        ]
        indexes = [models.Index(fields=["branch", "is_active"])]

    def __str__(self):
        return f"Employee({self.employee_code})"

    # F-281 PII seam: read/write bank account through one place.
    def get_bank_account(self) -> str:
        return self.bank_account


class BranchFaculty(BaseModel):
    """A faculty's assignment to a branch; exactly one is the salary branch (F-161/D5)."""

    faculty = models.ForeignKey(
        "accounts.User", on_delete=models.CASCADE, related_name="branch_assignments"
    )
    branch = models.ForeignKey(
        "organizations.Branch", on_delete=models.CASCADE, related_name="branch_faculty"
    )
    is_salary_branch = models.BooleanField(default=False)
    role_at_branch = models.JSONField(default=dict, blank=True)

    class Meta:
        db_table = "hr_branch_faculty"
        constraints = [
            models.UniqueConstraint(
                fields=["faculty", "branch"],
                condition=models.Q(is_active=True),
                name="unique_faculty_per_branch",
            ),
            # Exactly one salary branch per faculty (partial unique).
            models.UniqueConstraint(
                fields=["faculty"],
                condition=models.Q(is_salary_branch=True, is_active=True),
                name="unique_salary_branch_per_faculty",
            ),
        ]

    def __str__(self):
        return f"BranchFaculty({self.faculty_id}@{self.branch_id})"
