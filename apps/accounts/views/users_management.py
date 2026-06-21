"""Admin user-management screen — aggregate (GET) + write actions (POST)."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.interactors import user_management as um
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.accounts.queries.user import list_managed_users, list_pending_invites


class UserManagementView(APIView):
    """GET → { users, pending_invites, multi_role_policy }."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        tenant_id = request.user.tenant_id
        invites = list(list_pending_invites(tenant_id))

        # Newest-first: first invite seen per user is the most recent.
        invite_by_user: dict[str, object] = {}
        for inv in invites:
            invite_by_user.setdefault(str(inv.user_id), inv)

        users = [
            um.managed_user_dict(u, invite_by_user.get(str(u.id)))
            for u in list_managed_users(tenant_id)
        ]

        return Response({
            "users": users,
            "pending_invites": [um.invite_dict(inv) for inv in invites],
            "multi_role_policy": um.MULTI_ROLE_POLICY,
        })

    def post(self, request) -> Response:
        result = um.create_user(
            admin=request.user,
            name=request.data.get("name", ""),
            email=request.data.get("email", ""),
            phone=request.data.get("phone", ""),
            role=request.data.get("role"),
            send_invite=bool(request.data.get("send_invite", True)),
        )
        return Response(result, status=status.HTTP_201_CREATED)


class UserManagementActionView(APIView):
    """POST { action, userId } → dispatch an admin action on a user."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        admin = request.user
        action = request.data.get("action")
        user_id = request.data.get("userId")

        if action in {"deactivate", "activate"}:
            return Response(um.set_active(
                admin=admin, user_id=user_id, is_active=(action == "activate"),
            ))
        if action == "send_invite":
            return Response(um.send_invite(admin=admin, user_id=user_id))
        if action == "reset_password":
            return Response(um.reset_password(admin=admin, user_id=user_id))
        if action == "hard_delete_student":
            return Response(um.hard_delete_student(admin=admin, user_id=user_id))
        if action == "promote_student_to_faculty":
            return Response(um.promote_student_to_faculty(admin=admin, user_id=user_id))

        return Response({"error": "Unknown action"}, status=status.HTTP_400_BAD_REQUEST)


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
