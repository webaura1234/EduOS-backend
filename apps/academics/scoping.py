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

    Resolution order: explicit branch_id → body branchId → query ?branch= → user's own branch.
    The branch must belong to the caller's tenant.
    """
    body_branch = None
    if hasattr(request, "data") and isinstance(getattr(request, "data", None), dict):
        body_branch = request.data.get("branchId") or request.data.get("branch")
    bid = (
        branch_id
        or body_branch
        or request.query_params.get("branch")
        or getattr(request.user, "branch_id", None)
    )
    if bid in ("", "all"):
        bid = getattr(request.user, "branch_id", None)
    if not bid:
        raise ValidationError("A branch must be specified (branchId).")

    branch = get_branch(request.user.tenant_id, bid)
    if branch is None:
        raise NotFound("Branch not found in your institution.")
    return branch
