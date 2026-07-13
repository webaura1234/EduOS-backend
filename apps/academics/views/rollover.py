"""Views — Academic year rollover (retired — use Promotion execution)."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.exceptions import (
    PROMOTION_WORKSPACE_PATH,
    RolloverDirectExecutionDisabledError,
)
from apps.academics.permissions import IsAdminOrSuperAdmin


def _rollover_disabled_response() -> Response:
    return Response(
        {
            "detail": RolloverDirectExecutionDisabledError.default_detail,
            "code": RolloverDirectExecutionDisabledError.default_code,
            "promotionPath": PROMOTION_WORKSPACE_PATH,
        },
        status=status.HTTP_410_GONE,
    )


class RolloverPreviewView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        return _rollover_disabled_response()


class RolloverExecuteView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        return _rollover_disabled_response()


class RolloverUndoView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request):
        return _rollover_disabled_response()


class RolloverStatusView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request):
        return _rollover_disabled_response()
