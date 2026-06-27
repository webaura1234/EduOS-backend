"""Faculty account → Profile tab: view/edit own profile + change password."""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsFaculty


def _form(user, profile) -> dict:
    return {
        "userId": str(user.id),
        "name": user.full_name,
        "ownPhone": user.phone or None,
        "customLoginId": user.custom_login_id,
        "designation": (profile.designation if profile else "") or "",
        "department": (profile.department if profile else "") or "",
        "editableFields": ["name", "ownPhone"],
    }


class FacultyProfileFormView(APIView):
    """GET → FacultyProfileFormData; PATCH → update name/ownPhone; POST → change password."""

    permission_classes = [IsAuthenticated, IsFaculty]

    def _context(self, request):
        user = request.user
        profile = getattr(user, "faculty_profile", None)
        return user, profile

    def get(self, request) -> Response:
        resolve_branch(request)
        user, profile = self._context(request)
        return Response(_form(user, profile))

    def patch(self, request) -> Response:
        user, profile = self._context(request)
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
        return Response({"profile": _form(user, profile), "name": user.full_name})

    def post(self, request) -> Response:
        """Change password: requires currentPassword + newPassword."""
        user = request.user
        current = request.data.get("currentPassword") or ""
        new = request.data.get("newPassword") or ""
        if not user.check_password(current):
            return Response(
                {"error": "Current password is incorrect."},
                status=http.HTTP_400_BAD_REQUEST,
            )
        if len(new) < 8:
            return Response(
                {"error": "New password must be at least 8 characters."},
                status=http.HTTP_400_BAD_REQUEST,
            )
        user.set_password(new)
        user.save(update_fields=["password"])
        return Response({"success": True})
