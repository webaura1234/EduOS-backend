"""Queries — Employee + BranchFaculty (all ORM here)."""

from apps.hr.models import BranchFaculty, Employee


def get_employee(branch_id, employee_id) -> Employee | None:
    try:
        return Employee.objects.select_related("user", "branch").get(
            branch_id=branch_id, pk=employee_id, is_active=True
        )
    except (Employee.DoesNotExist, ValueError, TypeError):
        return None


def get_employee_for_user(user_id) -> Employee | None:
    try:
        return Employee.objects.select_related("user", "branch").get(
            user_id=user_id, is_active=True
        )
    except (Employee.DoesNotExist, ValueError, TypeError):
        return None


def employee_code_taken(branch_id, employee_code, exclude_id=None) -> bool:
    qs = Employee.objects.filter(branch_id=branch_id, employee_code=employee_code, is_active=True)
    if exclude_id:
        qs = qs.exclude(pk=exclude_id)
    return qs.exists()


def list_employees(branch_id, *, active_only=True):
    qs = Employee.objects.filter(branch_id=branch_id).select_related("user", "branch")
    if active_only:
        qs = qs.filter(is_active=True)
    return qs.order_by("employee_code")


def list_faculty_without_employee(branch_id):
    """Faculty users in a branch who do not yet have an HR employee record."""
    from apps.accounts.models.user import Role, User

    linked = set(
        Employee.objects.filter(branch_id=branch_id, is_active=True).values_list("user_id", flat=True)
    )
    return (
        User.objects.filter(branch_id=branch_id, role=Role.FACULTY, is_active=True)
        .exclude(pk__in=linked)
        .order_by("first_name", "last_name")
    )


def create_employee(*, user_obj, branch, employee_code, employment_type, joined_at,
                    designation="", base_components=None, bank_account="", ifsc="", pan="",
                    user=None) -> Employee:
    return Employee.objects.create(
        user=user_obj, branch=branch, employee_code=employee_code,
        employment_type=employment_type, joined_at=joined_at, designation=designation,
        base_components=base_components or [], bank_account=bank_account, ifsc=ifsc, pan=pan,
        created_by=user, updated_by=user,
    )


def update_employee(employee: Employee, fields: dict, expected_version=None, user=None):
    """Version-checked update (EC-API-05). Returns (employee, None) or (None, current_version)."""
    if expected_version is not None and employee.version != expected_version:
        return None, employee.version
    for k, v in fields.items():
        setattr(employee, k, v)
    employee.version += 1
    if user:
        employee.updated_by = user
    employee.save(update_fields=list(fields.keys()) + ["version", "updated_by", "updated_at"])
    return employee, None


def deactivate_employee(employee: Employee, *, exited_at=None, user=None) -> Employee:
    """F-169 / EC-RBAC-07 — soft-deactivate ONLY this employee's record + its user row.

    Never touches linked rows: a faculty who is also a parent keeps the parent account.
    """
    employee.is_active = False
    if exited_at is not None:
        employee.exited_at = exited_at
    employee.version += 1
    if user:
        employee.updated_by = user
    employee.save(update_fields=["is_active", "exited_at", "version", "updated_by", "updated_at"])
    # Deactivate the single User row (not the linked group).
    u = employee.user
    if u.is_active:
        u.is_active = False
        u.save(update_fields=["is_active"])
    return employee


# ── BranchFaculty (multi-branch, F-161/D5) ────────────────────────────────────
def list_branch_faculty(faculty_id):
    return BranchFaculty.objects.filter(faculty_id=faculty_id, is_active=True).select_related("branch")


def salary_branch_for_faculty(faculty_id):
    return (
        BranchFaculty.objects.filter(
            faculty_id=faculty_id, is_salary_branch=True, is_active=True
        )
        .values_list("branch_id", flat=True)
        .first()
    )


def upsert_branch_faculty(*, faculty, branch, is_salary_branch=False, role_at_branch=None,
                          user=None) -> BranchFaculty:
    if is_salary_branch:
        # Enforce exactly one salary branch: clear any existing salary flag first.
        BranchFaculty.objects.filter(
            faculty=faculty, is_salary_branch=True, is_active=True
        ).exclude(branch=branch).update(is_salary_branch=False)
    bf, _ = BranchFaculty.objects.update_or_create(
        faculty=faculty, branch=branch,
        defaults=dict(is_salary_branch=is_salary_branch, role_at_branch=role_at_branch or {},
                      is_active=True, created_by=user, updated_by=user),
    )
    return bf
