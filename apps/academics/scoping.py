"""
Branch resolution + tenant isolation for academics endpoints.

Academics data is branch-scoped. An admin operates on their own branch; a
super-admin must name a branch (?branch=<id> or branchId in body). The chosen
branch is always validated against the caller's tenant.
"""

from rest_framework.exceptions import NotFound, ValidationError

from apps.organizations.queries.branch import get_branch


def resolve_branch(request, branch_id=None):
    """Return a Branch the caller is allowed to act on, or raise.

    Resolution order: explicit branch_id → the user's own branch.
    The branch must belong to the caller's tenant.
    """
    bid = branch_id or request.query_params.get("branch") or getattr(request.user, "branch_id", None)
    if not bid:
        raise ValidationError("A branch must be specified (branchId).")

    branch = get_branch(request.user.tenant_id, bid)
    if branch is None:
        raise NotFound("Branch not found in your institution.")
    return branch
