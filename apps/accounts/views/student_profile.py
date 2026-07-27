"""Student account → Profile tab: view/edit own profile + change password."""

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsStudent
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile
from apps.accounts.services.avatar import avatar_url_for_user

_PHONE_CHANGE_DISABLED = "Phone number cannot be changed here. Contact your institution office."


def _class_label(enrollment) -> str:
    batch = enrollment.batch if enrollment else None
    if not batch:
        return ""
    course = batch.course.name if batch.course_id else ""
    return f"{course} - {batch.name}" if course else batch.name


def _form(user, profile, enrollment) -> dict:
    return {
        "userId": str(user.id),
        "name": user.full_name,
        # Guardian contact is read-only; ownPhone is display-only.
        "phone": (profile.guardian_phone if profile else None) or None,
        "ownPhone": user.phone or None,
        "customLoginId": user.custom_login_id,
        "classLabel": _class_label(enrollment),
        "rollNumber": user.custom_login_id,
        "editableFields": ["name"],
        "avatarUrl": avatar_url_for_user(user),
    }


class StudentProfileFormView(APIView):
    """GET → StudentProfileFormData; PATCH → update name; POST → change password."""
    permission_classes = [IsAuthenticated, IsStudent]

    def _context(self, request):
        user = request.user
        profile = getattr(user, "student_profile", None)
        enrollment = get_active_enrollment_for_profile(profile.pk) if profile else None
        return user, profile, enrollment

    def get(self, request) -> Response:
        resolve_branch(request)  # ensures tenant scoping/validation
        user, profile, enrollment = self._context(request)
        return Response(_form(user, profile, enrollment))

    def patch(self, request) -> Response:
        user, profile, enrollment = self._context(request)
        changed = []
        if "name" in request.data:
            name = (request.data.get("name") or "").strip()
            if name:
                first, _, last = name.partition(" ")
                user.first_name = first
                user.last_name = last
                changed += ["first_name", "last_name"]
        if "ownPhone" in request.data:
            return Response(
                {"error": _PHONE_CHANGE_DISABLED},
                status=http.HTTP_400_BAD_REQUEST,
            )
        if changed:
            user.save(update_fields=changed)
        return Response({"profile": _form(user, profile, enrollment), "name": user.full_name})

    def post(self, request) -> Response:
        """Change password: requires currentPassword + newPassword."""
        user = request.user
        current = request.data.get("currentPassword") or ""
        new = request.data.get("newPassword") or ""
        if not user.check_password(current):
            return Response({"error": "Current password is incorrect."},
                            status=http.HTTP_400_BAD_REQUEST)
        if len(new) < 8:
            return Response({"error": "New password must be at least 8 characters."},
                            status=http.HTTP_400_BAD_REQUEST)
        user.set_password(new)
        user.save(update_fields=["password"])
        return Response({"success": True})
