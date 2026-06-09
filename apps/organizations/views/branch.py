"""
Branch views (super-admin) — list, create, activate/deactivate.

Thin views: validate via serializer → call queries → return serialized data.
All DB access lives in apps.organizations.queries.branch.
"""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsSuperAdmin
from apps.organizations.queries import branch as branch_q
from apps.organizations.serializers.branch import (
    BranchSerializer,
    CreateBranchSerializer,
    SetBranchActiveSerializer,
)


class BranchListCreateView(APIView):
    """
    GET  /api/v1/organizations/branches/  → { "branches": [...] }
    POST /api/v1/organizations/branches/  → { "branch": {...} }
    Super-admin only; scoped to the caller's tenant.
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def get(self, request) -> Response:
        branches = branch_q.list_branches(request.user.tenant_id)
        return Response({"branches": BranchSerializer(branches, many=True).data})

    def post(self, request) -> Response:
        serializer = CreateBranchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        tenant_id = request.user.tenant_id

        if branch_q.branch_name_exists(tenant_id, data["name"]):
            return Response(
                {"error": "A branch with this name already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if branch_q.branch_code_exists(tenant_id, data.get("code", "")):
            return Response(
                {"error": "A branch with this code already exists."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        branch = branch_q.create_branch(
            tenant_id, name=data["name"], code=data.get("code", ""), city=data.get("city", "")
        )
        return Response(
            {"branch": BranchSerializer(branch).data}, status=status.HTTP_201_CREATED
        )


class BranchActionsView(APIView):
    """
    PATCH /api/v1/organizations/branches/actions/
        { "action": "set_active", "branchId": "...", "isActive": true }
    """
    permission_classes = [IsAuthenticated, IsSuperAdmin]

    def patch(self, request) -> Response:
        serializer = SetBranchActiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        branch = branch_q.get_branch(request.user.tenant_id, data["branchId"])
        if branch is None:
            return Response({"error": "Branch not found."}, status=status.HTTP_404_NOT_FOUND)

        branch = branch_q.set_branch_active(branch, data["isActive"])
        return Response({"branch": BranchSerializer(branch).data})
