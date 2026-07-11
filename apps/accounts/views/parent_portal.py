"""Parent portal endpoints used by the child switcher BFF."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsParent
from apps.accounts.queries.parent import list_portal_children, parent_portal_access


class ParentPortalAccessView(APIView):
    permission_classes = [IsAuthenticated, IsParent]

    def get(self, request) -> Response:
        return Response(parent_portal_access(request.user.tenant))


class ParentChildrenView(APIView):
    permission_classes = [IsAuthenticated, IsParent]

    def get(self, request) -> Response:
        access = parent_portal_access(request.user.tenant)
        if not access.get("allowed"):
            return Response(access)
        return Response(list_portal_children(request.user))
