"""Admin Guardian-links overview — the GuardianManagementData aggregate."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.models.guardian import CustodyType, default_notification_channels
from apps.accounts.models.user import Role, User
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.accounts.queries import guardian as g_q
from apps.accounts.queries.guardian import list_guardian_links
from apps.attendance.queries import roster as roster_q


def _student_id(student_user) -> str:
    profile = getattr(student_user, "student_profile", None)
    return str(profile.id) if profile else str(student_user.id)


def _notification_out(link) -> dict:
    channels = link.notification_channels or default_notification_channels()
    return {
        "in_app": bool(channels.get("in_app", True)),
        "sms": bool(channels.get("sms", True)),
        "email": bool(channels.get("email", True)),
    }


def _notification_in(payload) -> dict:
    raw = payload.get("receivesNotifications") or {}
    return {
        "in_app": bool(raw.get("in_app", True)),
        "sms": bool(raw.get("sms", True)),
        "email": bool(raw.get("email", True)),
    }


def _link(link) -> dict:
    return {
        "id": str(link.id),
        "studentId": _student_id(link.student),
        "studentName": link.student.full_name,
        "guardianUserId": str(link.guardian_id),
        "guardianName": link.guardian.full_name,
        "relationship": link.relationship,
        "hasPortalAccess": link.has_portal_access,
        "isPrimaryContact": link.is_primary_contact,
        "canPickup": link.can_pickup,
        "receivesNotifications": _notification_out(link),
        "createdAt": link.created_at.isoformat(),
    }


class AdminGuardianOverviewView(APIView):
    """GET → { links, students, guardians }."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        links = list(list_guardian_links(branch.pk))

        class_by_profile = {
            str(e.student_profile_id): (e.current_batch.name if e.current_batch_id else "")
            for e in roster_q.all_active_students_in_branch(branch.pk)
        }
        students = []
        for u in (
            User.objects.filter(
                tenant_id=branch.tenant_id, branch_id=branch.pk,
                role=Role.STUDENT, is_active=True,
            )
            .select_related("student_profile")
            .order_by("first_name", "last_name")
        ):
            profile = getattr(u, "student_profile", None)
            sid = str(profile.id) if profile else str(u.id)
            students.append({
                "studentId": sid,
                "studentName": u.full_name,
                "classLabel": class_by_profile.get(sid, ""),
            })

        guardians = {
            str(u.id): u.full_name
            for u in User.objects.filter(
                tenant_id=branch.tenant_id, branch_id=branch.pk,
                role=Role.PARENT, is_active=True,
            )
        }
        for link in links:
            guardians.setdefault(str(link.guardian_id), link.guardian.full_name)

        return Response({
            "links": [_link(link) for link in links],
            "students": students,
            "guardians": [{"userId": uid, "name": name} for uid, name in guardians.items()],
        })


class AdminGuardianActionView(APIView):
    """POST { action, payload?/linkId } → save / remove / set-primary a guardian link."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        user = request.user
        action = request.data.get("action")

        if action == "save_link":
            p = request.data.get("payload") or {}
            channels = _notification_in(p)
            link_id = p.get("id")
            if link_id:
                link = g_q.get_link(branch.pk, link_id)
                if link is None:
                    return Response({"error": "Link not found."}, status=status.HTTP_404_NOT_FOUND)
                g_q.update_link(link, {
                    "relationship": p.get("relationship", link.relationship),
                    "has_portal_access": bool(p.get("hasPortalAccess", link.has_portal_access)),
                    "is_primary_contact": bool(p.get("isPrimaryContact", link.is_primary_contact)),
                    "can_pickup": bool(p.get("canPickup", link.can_pickup)),
                    "notification_channels": channels,
                }, user=user)
                if link.is_primary_contact:
                    g_q.set_primary_link(link, user=user)
                return Response({"id": str(link.id)})

            student_user = g_q.student_user_from_profile(branch.pk, p.get("studentId"))
            guardian = g_q.guardian_user(branch.pk, p.get("guardianUserId"))
            if student_user is None or guardian is None:
                return Response({"error": "Student or guardian not found."},
                                status=status.HTTP_400_BAD_REQUEST)
            link = g_q.create_link(
                student_user=student_user, guardian_user=guardian,
                relationship=p.get("relationship", "guardian"),
                custody=CustodyType.PRIMARY,
                is_primary=bool(p.get("isPrimaryContact")),
                has_portal=bool(p.get("hasPortalAccess", True)),
                can_pickup=bool(p.get("canPickup", True)),
                notification_channels=channels,
                user=user,
            )
            if link.is_primary_contact:
                g_q.set_primary_link(link, user=user)
            return Response({"id": str(link.id)}, status=status.HTTP_201_CREATED)

        if action == "remove_link":
            link = g_q.get_link(branch.pk, request.data.get("linkId"))
            if link is None:
                return Response({"error": "Link not found."}, status=status.HTTP_404_NOT_FOUND)
            g_q.remove_link(link, user=user)
            return Response({"ok": True})

        if action == "set_primary":
            link = g_q.get_link(branch.pk, request.data.get("linkId"))
            if link is None:
                return Response({"error": "Link not found."}, status=status.HTTP_404_NOT_FOUND)
            g_q.set_primary_link(link, user=user)
            return Response({"id": str(link.id), "isPrimaryContact": True})

        return Response({"error": "Unknown action."}, status=status.HTTP_400_BAD_REQUEST)
