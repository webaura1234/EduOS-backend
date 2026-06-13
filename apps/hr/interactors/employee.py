"""Interactors — employee master + multi-branch assignment (F-156/161/169)."""

from django.db import transaction
from rest_framework.exceptions import ValidationError

from apps.hr.queries import employee as emp_q


@transaction.atomic
def create_employee(*, branch, user_obj, employee_code, employment_type, joined_at,
                    designation="", base_components=None, bank_account="", ifsc="", pan="",
                    actor=None):
    if not employee_code or not employee_code.strip():
        raise ValidationError({"employeeCode": "Employee code is required."})
    if emp_q.employee_code_taken(branch.pk, employee_code):
        raise ValidationError({"employeeCode": "This employee code is already in use."})
    if emp_q.get_employee_for_user(user_obj.pk):
        raise ValidationError({"user": "This user already has an employee record."})
    return emp_q.create_employee(
        user_obj=user_obj, branch=branch, employee_code=employee_code,
        employment_type=employment_type, joined_at=joined_at, designation=designation,
        base_components=base_components, bank_account=bank_account, ifsc=ifsc, pan=pan,
        user=actor,
    )


@transaction.atomic
def deactivate_employee(*, employee, exited_at=None, actor=None):
    """F-169 / EC-RBAC-07 — deactivate only this employee + its single user row."""
    return emp_q.deactivate_employee(employee, exited_at=exited_at, user=actor)


@transaction.atomic
def assign_branch(*, faculty_user, branch, is_salary_branch=False, role_at_branch=None, actor=None):
    """F-161 — assign a faculty to a branch; enforce one salary branch (D5)."""
    return emp_q.upsert_branch_faculty(
        faculty=faculty_user, branch=branch, is_salary_branch=is_salary_branch,
        role_at_branch=role_at_branch, user=actor,
    )
