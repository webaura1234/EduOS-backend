"""Views — Academic year rollover."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.interactors import rollover as rol_i
from apps.academics.permissions import IsAdminOrSuperAdmin
from apps.academics.scoping import resolve_branch
from apps.academics.serializers.rollover import RolloverExecuteSerializer, RolloverPreviewSerializer


class RolloverPreviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId") if request.data else None)
        serializer = RolloverPreviewSerializer(data=request.data or {})
        serializer.is_valid(raise_exception=True)
        preview = rol_i.build_preview(branch.pk, request.user.tenant)
        return Response(preview.to_dict())


class RolloverExecuteView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId"))
        serializer = RolloverExecuteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = rol_i.execute_rollover(
            branch=branch,
            tenant=request.user.tenant,
            expected_version=data["expectedVersion"],
            user=request.user,
        )
        return Response(result, status=status.HTTP_202_ACCEPTED if result.get("async") else status.HTTP_200_OK)


class RolloverUndoView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request, request.data.get("branchId") if request.data else None)
        result = rol_i.undo_rollover(branch_id=branch.pk, user=request.user)
        return Response(result)


class RolloverStatusView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        return Response(rol_i.get_rollover_status(branch.pk))
