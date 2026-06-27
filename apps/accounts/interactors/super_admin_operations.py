"""Super-admin operations overview — branch roll-ups for the Operations screen."""

from apps.accounts.models.user import Role
from apps.accounts.queries.user import count_active_by_role_in_branch
from apps.attendance.queries import roster as roster_q
from apps.organizations.queries.branch import list_branches


def operations_overview(tenant) -> dict:
    """Per-branch people counts + institution totals."""
    branches = list(list_branches(tenant.pk))
    rows = []
    totals = {"admins": 0, "faculty": 0, "students": 0, "parents": 0}

    for branch in branches:
        admins = count_active_by_role_in_branch(branch.pk, Role.ADMIN)
        faculty = count_active_by_role_in_branch(branch.pk, Role.FACULTY)
        students = roster_q.all_active_students_in_branch(branch.pk).count()
        parents = count_active_by_role_in_branch(branch.pk, Role.PARENT)

        totals["admins"] += admins
        totals["faculty"] += faculty
        totals["students"] += students
        totals["parents"] += parents

        rows.append({
            "branchId": str(branch.pk),
            "branchName": branch.name,
            "code": branch.code or "",
            "city": branch.city or "",
            "isActive": branch.is_active,
            "admins": admins,
            "faculty": faculty,
            "students": students,
            "parents": parents,
        })

    return {
        "branches": rows,
        "totals": totals,
    }
