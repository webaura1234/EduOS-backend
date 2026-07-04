"""Super-admin operations overview — branch roll-ups for the Operations screen."""

from apps.accounts.models.user import Role
from apps.accounts.queries.user import count_active_by_role_grouped_by_branch
from apps.attendance.queries import roster as roster_q
from apps.organizations.queries.branch import list_branches


def operations_overview(tenant) -> dict:
    """Per-branch people counts + institution totals.

    Uses tenant-wide grouped counts (one query per role + one for students) instead of
    a per-branch round-trip, so cost is O(1) queries rather than O(branches).
    """
    branches = list(list_branches(tenant.pk))
    branch_ids = [b.pk for b in branches]

    admins_by_branch = count_active_by_role_grouped_by_branch(tenant.pk, Role.ADMIN)
    faculty_by_branch = count_active_by_role_grouped_by_branch(tenant.pk, Role.FACULTY)
    parents_by_branch = count_active_by_role_grouped_by_branch(tenant.pk, Role.PARENT)
    students_by_branch = roster_q.active_student_counts_by_branch(branch_ids)

    rows = []
    totals = {"admins": 0, "faculty": 0, "students": 0, "parents": 0}

    for branch in branches:
        admins = admins_by_branch.get(branch.pk, 0)
        faculty = faculty_by_branch.get(branch.pk, 0)
        students = students_by_branch.get(branch.pk, 0)
        parents = parents_by_branch.get(branch.pk, 0)

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
