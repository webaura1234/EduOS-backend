"""Admin Guardian-links overview — the GuardianManagementData aggregate."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.models.user import Role, User
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.accounts.queries import guardian as g_q
from apps.accounts.queries.guardian import list_guardian_links
from apps.attendance.queries import roster as roster_q

# Backend custody vocab → frontend CustodyType.
_CUSTODY = {"primary": "full", "shared": "shared", "emergency": "visitation"}
# Frontend CustodyType → backend custody vocab.
_CUSTODY_IN = {"full": "primary", "shared": "shared", "visitation": "emergency",
               "none": "emergency"}


def _student_id(student_user) -> str:
    # FE studentId = StudentProfile id (matches the students list); fall back to user id.
    profile = getattr(student_user, "student_profile", None)
    return str(profile.id) if profile else str(student_user.id)


def _link(link) -> dict:
    return {
        "id": str(link.id),
        "studentId": _student_id(link.student),
        "studentName": link.student.full_name,
        "guardianUserId": str(link.guardian_id),
        "guardianName": link.guardian.full_name,
        "relationship": link.relationship,
        "custodyType": _CUSTODY.get(link.custody, "full"),
        "hasPortalAccess": link.has_portal_access,
        "isPrimaryContact": link.is_primary_contact,
        # Per-link channel routing isn't modelled yet — default to all channels on.
        "receivesNotifications": {"in_app": True, "sms": True, "email": True},
        "createdAt": link.created_at.isoformat(),
    }


class AdminGuardianOverviewView(APIView):
    """GET → { links, students, guardians }."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        links = list(list_guardian_links(branch.pk))

        # Class label where the student has an active enrollment (best-effort).
        class_by_profile = {
            str(e.student_profile_id): (e.current_batch.name if e.current_batch_id else "")
            for e in roster_q.all_active_students_in_branch(branch.pk)
        }
        # List ALL student users in the branch (a guardian can be linked even before
        # the student is enrolled), not only enrolled ones.
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

        # Guardians = parent users in the branch (plus any already linked).
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
            custody = _CUSTODY_IN.get(p.get("custodyType"), "primary")
            link_id = p.get("id")
            if link_id:
                link = g_q.get_link(branch.pk, link_id)
                if link is None:
                    return Response({"error": "Link not found."}, status=status.HTTP_404_NOT_FOUND)
                g_q.update_link(link, {
                    "relationship": p.get("relationship", link.relationship),
                    "custody": custody,
                    "has_portal_access": bool(p.get("hasPortalAccess", link.has_portal_access)),
                    "is_primary_contact": bool(p.get("isPrimaryContact", link.is_primary_contact)),
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
                relationship=p.get("relationship", "guardian"), custody=custody,
                is_primary=bool(p.get("isPrimaryContact")),
                has_portal=bool(p.get("hasPortalAccess", True)), user=user,
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
