"""Parent account → Profile tab: view/edit own profile + linked children."""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsParent
from apps.accounts.queries.parent import list_portal_children
from apps.accounts.services.avatar import avatar_url_for_user


def _form(user) -> dict:
    return {
        "userId": str(user.id),
        "name": user.full_name,
        "phone": user.phone or None,
        "email": user.email or None,
        "ownPhone": user.phone or None,
        "avatarUrl": avatar_url_for_user(user),
        "children": list_portal_children(user),
        "editableFields": ["name"],
    }


class ParentProfileFormView(APIView):
    """GET → parent profile; PATCH → update display name."""

    permission_classes = [IsAuthenticated, IsParent]

    def get(self, request) -> Response:
        return Response(_form(request.user))

    def patch(self, request) -> Response:
        user = request.user
        changed = []
        if "name" in request.data:
            name = (request.data.get("name") or "").strip()
            if name:
                first, _, last = name.partition(" ")
                user.first_name = first
                user.last_name = last
                changed += ["first_name", "last_name"]
        if changed:
            user.save(update_fields=changed)
        return Response({"profile": _form(user), "name": user.full_name})
