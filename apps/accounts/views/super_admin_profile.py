"""Super Admin account → Profile tab: view/edit own profile."""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.permissions import IsSuperAdmin
from apps.accounts.services.avatar import avatar_url_for_user


def _form(user) -> dict:
    tenant = user.tenant
    return {
        "userId": str(user.id),
        "name": user.full_name,
        "phone": user.phone or None,
        "ownPhone": user.phone or None,
        "email": user.email or None,
        "avatarUrl": avatar_url_for_user(user),
        "institutionName": tenant.name if tenant else None,
        "institutionType": tenant.institution_type if tenant else None,
        "editableFields": ["name", "ownPhone"],
    }


class SuperAdminProfileFormView(APIView):
    """GET → SuperAdminProfileData; PATCH → update name/ownPhone."""

    permission_classes = [IsAuthenticated, IsSuperAdmin]

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
        if "ownPhone" in request.data:
            user.phone = (request.data.get("ownPhone") or "").strip() or None
            changed.append("phone")
        if changed:
            user.save(update_fields=changed)
        return Response({"profile": _form(user), "name": user.full_name})
