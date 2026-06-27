"""Branch resolution for admin screens that support super-admin tenant-wide scope."""

from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.models.user import Role
from apps.academics.scoping import resolve_branch as resolve_academic_branch
from apps.organizations.queries.branch import get_branch


def resolve_management_scope(request):
    """Return (branch_or_none, branch_scope_label) for user/guardian management.

    - Branch admin: their branch, scope = branch uuid string.
    - Super admin + ?branch=all or omitted: tenant-wide, scope = "all".
    - Super admin + ?branch=<uuid>: that branch.
    """
    user = request.user
    if user.role != Role.SUPER_ADMIN:
        branch = resolve_academic_branch(request)
        return branch, str(branch.pk)

    param = (
        request.query_params.get("branch")
        or request.data.get("branchId")
        or request.data.get("branch")
    )
    if not param or param == "all":
        return None, "all"

    branch = get_branch(user.tenant_id, param)
    if branch is None:
        raise NotFound("Branch not found in your institution.")
    return branch, str(branch.pk)
