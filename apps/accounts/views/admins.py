"""Super-admin branch-admin management (list / invite / activate / reassign)."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models.user import Role
from apps.accounts.permissions import IsSuperAdmin
from apps.accounts.queries.user import (
    create_invited_user,
    get_admin_in_tenant,
    list_admins_in_tenant,
    set_user_active,
    set_user_branch,
)
from apps.accounts.serializers.auth import (
    BranchAdminSerializer,
    InviteAdminSerializer,
    UpdateAdminSerializer,
)
from apps.organizations.queries.branch import get_branch, list_branches


class SuperAdminAdminsView(APIView):
    """GET → list branch admins + branches; POST → invite a new branch admin."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request) -> Response:
        tenant_id = request.user.tenant_id
        admins = list_admins_in_tenant(tenant_id)
        branches = list_branches(tenant_id)
        return Response({
            "admins": BranchAdminSerializer(admins, many=True).data,
            "branches": [{"id": str(b.id), "name": b.name} for b in branches],
        })

    def post(self, request) -> Response:
        serializer = InviteAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        branch = get_branch(request.user.tenant_id, data["branchId"])
        if branch is None:
            return Response({"branchId": "Branch not found in your institution."},
                            status=status.HTTP_404_NOT_FOUND)

        parts = data["name"].strip().split(" ", 1)
        user = create_invited_user(
            first_name=parts[0],
            last_name=parts[1] if len(parts) > 1 else "",
            role=Role.ADMIN,
            tenant_id=request.user.tenant_id,
            branch_id=branch.id,
            phone=data["phone"],
            custom_login_id=None,
            email=None,
            created_by=request.user,
        )
        return Response({"admin": BranchAdminSerializer(user).data},
                        status=status.HTTP_201_CREATED)


class SuperAdminAdminDetailView(APIView):
    """PATCH → activate/deactivate and/or reassign a branch admin's branch."""
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def patch(self, request, admin_id) -> Response:
        admin = get_admin_in_tenant(request.user.tenant_id, admin_id)
        if admin is None:
            return Response({"error": "Admin not found."}, status=status.HTTP_404_NOT_FOUND)

        serializer = UpdateAdminSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if "isActive" in data:
            admin = set_user_active(admin, data["isActive"])
        if "branchId" in data:
            branch = get_branch(request.user.tenant_id, data["branchId"])
            if branch is None:
                return Response({"branchId": "Branch not found in your institution."},
                                status=status.HTTP_404_NOT_FOUND)
            admin = set_user_branch(admin, branch.id)

        return Response({"admin": BranchAdminSerializer(admin).data})
