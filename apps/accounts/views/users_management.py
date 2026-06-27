"""Admin user-management screen — aggregate (GET) + write actions (POST)."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.scoping import resolve_management_scope
from apps.accounts.interactors import user_management as um
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.accounts.queries.user import list_managed_users, list_pending_invites
from apps.accounts.models.user import Role
from apps.organizations.queries.branch import get_branch


class UserManagementView(APIView):
    """GET → { users, pending_invites, multi_role_policy, branchId, branchName, branchScope }."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch, branch_scope = resolve_management_scope(request)
        tenant_id = request.user.tenant_id
        branch_id = branch.pk if branch else None
        invites = list(list_pending_invites(tenant_id, branch_id=branch_id))

        invite_by_user: dict[str, object] = {}
        for inv in invites:
            invite_by_user.setdefault(str(inv.user_id), inv)

        users = [
            um.managed_user_dict(u, invite_by_user.get(str(u.id)))
            for u in list_managed_users(tenant_id, branch_id=branch_id)
        ]

        return Response({
            "users": users,
            "pending_invites": [um.invite_dict(inv) for inv in invites],
            "multi_role_policy": um.MULTI_ROLE_POLICY,
            "branchScope": branch_scope,
            "branchId": str(branch.pk) if branch else None,
            "branchName": branch.name if branch else None,
        })

    def post(self, request) -> Response:
        branch_id = None
        if request.user.role == Role.SUPER_ADMIN:
            raw = request.data.get("branchId") or request.data.get("branch")
            if not raw:
                return Response(
                    {"error": "branchId is required when creating users as super admin."},
                    status=400,
                )
            branch = get_branch(request.user.tenant_id, raw)
            if branch is None:
                return Response({"error": "Branch not found."}, status=404)
            branch_id = branch.pk

        result = um.create_user(
            admin=request.user,
            name=request.data.get("name", ""),
            email=request.data.get("email", ""),
            phone=request.data.get("phone", ""),
            role=request.data.get("role"),
            send_invite=bool(request.data.get("send_invite", True)),
            branch_id=branch_id,
            batch_id=request.data.get("batchId"),
        )
        return Response(result, status=201)


class UserManagementActionView(APIView):
    """POST { action, userId } → dispatch an admin action on a user."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        admin = request.user
        action = request.data.get("action")
        user_id = request.data.get("userId")
        branch_filter = None
        if admin.role != Role.SUPER_ADMIN:
            branch_filter = admin.branch_id

        if action in {"deactivate", "activate"}:
            return Response(um.set_active(
                admin=admin, user_id=user_id, is_active=(action == "activate"),
                branch_id=branch_filter,
            ))
        if action == "send_invite":
            return Response(um.send_invite(admin=admin, user_id=user_id, branch_id=branch_filter))
        if action == "reset_password":
            return Response(um.reset_password(admin=admin, user_id=user_id, branch_id=branch_filter))
        if action == "hard_delete_student":
            return Response(um.hard_delete_student(admin=admin, user_id=user_id, branch_id=branch_filter))
        if action == "promote_student_to_faculty":
            return Response(um.promote_student_to_faculty(
                admin=admin, user_id=user_id, branch_id=branch_filter,
            ))
        if action == "update_user":
            payload = request.data.get("payload") or {}
            return Response(um.update_user(
                admin=admin,
                user_id=user_id,
                name=payload.get("name"),
                email=payload.get("email"),
                phone=payload.get("phone"),
                branch_id=branch_filter,
            ))

        return Response({"error": "Unknown action"}, status=400)


class CheckMultiRoleView(APIView):
    """POST { phone, email, role } → MultiRoleWarning | null."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        warning = um.check_multi_role(
            admin=request.user,
            phone=request.data.get("phone"),
            email=request.data.get("email"),
            role=request.data.get("role"),
        )
        return Response({"warning": warning})
