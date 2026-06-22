"""Announcement views — admin create/list + student feed."""

from rest_framework import status as http
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.models.user import Role, User
from apps.accounts.permissions import IsAdminOrSuperAdmin, IsStudent
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile
from apps.communications.queries import announcement as ann_q

_CHANNELS = ("in_app", "sms", "email")
_TARGET_LABELS = {"all": "Everyone", "role": "By role", "batch": "Class/Batch",
                  "department": "Department"}


def _announcement(a) -> dict:
    channels = a.channels or []
    return {
        "id": str(a.id),
        "title": a.title,
        "body": a.body,
        "targetType": a.target_type,
        "targetLabel": a.target_label or _TARGET_LABELS.get(a.target_type, ""),
        "scope": a.scope,
        "branchId": str(a.branch_id),
        "branchName": a.branch.name if a.branch_id else None,
        "channels": channels,
        "sentAt": a.created_at.isoformat(),
        "recipientCount": a.recipient_count,
        "deliveryStatus": {
            ch: ("sent" if ch in channels else "skipped") for ch in _CHANNELS
        },
    }


def _recipient_count(branch, target_type, target_value) -> int:
    qs = User.objects.filter(branch_id=branch.pk, is_active=True)
    if target_type == "role" and target_value:
        qs = qs.filter(role=target_value)
    elif target_type in ("batch", "department"):
        qs = qs.filter(role=Role.STUDENT)  # rough estimate; class roster not resolved here
    return qs.count()


class AdminAnnouncementsView(APIView):
    """GET → { announcements }; POST → create + broadcast (records the send)."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        rows = ann_q.list_for_branch(branch.pk)
        return Response({"announcements": [_announcement(a) for a in rows]})

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        title = (request.data.get("title") or "").strip()
        body = (request.data.get("body") or "").strip()
        if not title or not body:
            raise ValidationError({"title": "Title and body are required."})

        target_type = request.data.get("targetType", "all")
        target_value = str(request.data.get("targetValue", "") or "")
        channels = [c for c in (request.data.get("channels") or []) if c in _CHANNELS]

        announcement = ann_q.create_announcement(
            branch=branch, title=title, body=body, target_type=target_type,
            target_value=target_value, target_label=request.data.get("targetLabel", ""),
            channels=channels,
            recipient_count=_recipient_count(branch, target_type, target_value),
            user=request.user,
        )
        return Response({"announcement": _announcement(announcement)},
                        status=http.HTTP_201_CREATED)


class StudentAnnouncementsView(APIView):
    """GET → { announcements } visible to the logged-in student."""
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        profile = getattr(request.user, "student_profile", None)
        enrollment = get_active_enrollment_for_profile(profile.pk) if profile else None
        batch_id = enrollment.batch_id if enrollment else None
        rows = ann_q.list_for_student(branch.pk, batch_id=batch_id)
        return Response({"announcements": [_announcement(a) for a in rows]})


class FacultyAnnouncementsView(APIView):
    """GET → { announcements } visible to faculty (everyone + role=faculty/staff)."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        rows = ann_q.list_for_faculty(branch.pk)
        return Response({"announcements": [_announcement(a) for a in rows]})
