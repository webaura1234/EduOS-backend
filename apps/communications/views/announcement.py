"""Announcement views — admin create/list + student feed."""

from rest_framework import status as http
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import structure as struct_q
from apps.academics.scoping import resolve_branch
from apps.accounts.models.user import Role, User
from apps.accounts.permissions import IsAdminOrSuperAdmin, IsStudent
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile
from apps.communications.models import AnnouncementTargetType
from apps.communications.queries import announcement as ann_q

_CHANNELS = ("in_app", "sms", "email")
_TARGET_LABELS = {"all": "Everyone", "role": "By role", "batch": "Class/Batch",
                  "department": "Department"}
_VALID_TARGET_TYPES = {c.value for c in AnnouncementTargetType}


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


def _audience_options(branch) -> dict:
    """Dropdown options for the 'Target details' field, keyed by audience type."""
    classes = [
        {"value": str(b.id),
         "label": f"{b.course.name} - {b.name}" if b.course_id else b.name}
        for b in struct_q.list_batches(branch.pk)
    ]
    departments = [
        {"value": str(d.id), "label": d.name} for d in struct_q.list_departments(branch.pk)
    ]
    roles = [
        {"value": "student", "label": "Students"},
        {"value": "parent", "label": "Parents"},
        {"value": "faculty", "label": "Faculty"},
        {"value": "staff", "label": "Staff"},
    ]
    return {"batch": classes, "department": departments, "role": roles}


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
        return Response({
            "announcements": [_announcement(a) for a in rows],
            "options": _audience_options(branch),
        })

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        title = (request.data.get("title") or "").strip()
        body = (request.data.get("body") or "").strip()
        if not title or not body:
            raise ValidationError({"title": "Title and body are required."})

        target_type = request.data.get("targetType", "all")
        if target_type not in _VALID_TARGET_TYPES:
            raise ValidationError({"targetType": f"Invalid target type '{target_type}'."})
        target_value = str(request.data.get("targetValue", "") or "")
        channels = [c for c in (request.data.get("channels") or []) if c in _CHANNELS]

        announcement = ann_q.create_announcement(
            branch=branch, title=title, body=body, target_type=target_type,
            target_value=target_value, target_label=request.data.get("targetLabel", ""),
            channels=channels,
            recipient_count=_recipient_count(branch, target_type, target_value),
            user=request.user,
        )
        from apps.communications.interactors.announcement_emit import emit_announcement_notifications
        emit_announcement_notifications(announcement, created_by=request.user)
        return Response({"announcement": _announcement(announcement)},
                        status=http.HTTP_201_CREATED)


def _student_notices(request):
    """All notices visible to the logged-in student (newest first)."""
    branch = resolve_branch(request)
    profile = getattr(request.user, "student_profile", None)
    if not profile:
        return list(ann_q.list_for_student(branch.pk))
    enrollment = get_active_enrollment_for_profile(profile.pk)
    batch_id = enrollment.batch_id if enrollment else None
    department_id = None
    if enrollment and enrollment.batch_id and enrollment.batch.course_id:
        department_id = enrollment.batch.course.department_id
    return list(ann_q.list_for_student(
        branch.pk, batch_id=batch_id, department_id=department_id,
    ))


class StudentAnnouncementsView(APIView):
    """GET → { announcements, unreadCount } — all unread + the 5 most recent read.
    POST → marks all currently-visible notices read."""
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        rows = _student_notices(request)
        row_ids = [a.pk for a in rows]
        read_ids = ann_q.read_ids_for_user(request.user.pk, row_ids)
        unread = [a for a in rows if a.pk not in read_ids]
        recent_read_ids = ann_q.recent_read_for_user(request.user.pk, row_ids, limit=5)
        read_by_id = {a.pk: a for a in rows if a.pk in read_ids}
        recent_read = [read_by_id[aid] for aid in recent_read_ids if aid in read_by_id]
        visible = sorted(unread + recent_read, key=lambda a: a.created_at, reverse=True)

        def item(a):
            return {**_announcement(a), "read": a.pk in read_ids}

        return Response({
            "announcements": [item(a) for a in visible],
            "unreadCount": len(unread),
        })

    def post(self, request) -> Response:
        rows = _student_notices(request)
        ann_q.mark_read(request.user, rows)
        return Response({"success": True, "unreadCount": 0})


class StudentAnnouncementsUnreadView(APIView):
    """GET → { unreadCount } — lightweight count for the nav badge/glow."""
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        rows = _student_notices(request)
        read_ids = ann_q.read_ids_for_user(request.user.pk, [a.pk for a in rows])
        return Response({"unreadCount": sum(1 for a in rows if a.pk not in read_ids)})


class FacultyAnnouncementsView(APIView):
    """GET → { announcements } visible to faculty (everyone + role=faculty/staff)."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        rows = ann_q.list_for_faculty(branch.pk, faculty_user_id=request.user.pk)
        return Response({
            "announcements": [_announcement(a) for a in rows],
            "facultyBranchIds": [str(branch.id)],
            "facultyBranchNames": [branch.name],
        })
