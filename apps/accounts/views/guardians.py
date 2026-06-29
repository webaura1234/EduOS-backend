"""Admin Guardian-links overview — the GuardianManagementData aggregate."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.helpers import batch_display_label
from apps.accounts.scoping import resolve_management_scope
from apps.accounts.models.guardian import CustodyType, default_notification_channels
from apps.accounts.models.user import Role, User
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.accounts.queries import guardian as g_q
from apps.accounts.queries.guardian import list_guardian_links, list_guardian_links_for_tenant
from apps.attendance.queries import roster as roster_q
from apps.organizations.queries.branch import list_branches


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


def _link(link, *, class_label: str = "", branch_id=None, branch_name: str = "") -> dict:
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
        "classLabel": class_label,
        "branchId": str(branch_id) if branch_id else None,
        "branchName": branch_name,
    }


def _build_roster_context(tenant_id, *, single_branch=None):
    """Profile-id maps for class label and branch metadata."""
    class_by_profile: dict[str, str] = {}
    branch_by_profile: dict[str, tuple[str, str]] = {}
    branches = [single_branch] if single_branch else list(list_branches(tenant_id))
    for b in branches:
        if b is None:
            continue
        for e in roster_q.all_active_students_in_branch(b.pk):
            pid = str(e.student_profile_id)
            label = batch_display_label(e.current_batch) if e.current_batch_id else ""
            class_by_profile[pid] = label
            branch_by_profile[pid] = (str(b.pk), b.name)
    return class_by_profile, branch_by_profile


class AdminGuardianOverviewView(APIView):
    """GET → { links, students, guardians, branchScope }."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch, branch_scope = resolve_management_scope(request)
        tenant_id = request.user.tenant_id
        class_param = request.query_params.get("class")

        if branch:
            links = list(list_guardian_links(branch.pk))
            student_qs = User.objects.filter(
                tenant_id=tenant_id, branch_id=branch.pk,
                role=Role.STUDENT, is_active=True,
            )
            class_by_profile, branch_by_profile = _build_roster_context(
                tenant_id, single_branch=branch,
            )
            guardian_qs = User.objects.filter(
                tenant_id=tenant_id, branch_id=branch.pk,
                role=Role.PARENT, is_active=True,
            )
        else:
            links = list(list_guardian_links_for_tenant(tenant_id))
            student_qs = User.objects.filter(
                tenant_id=tenant_id, role=Role.STUDENT, is_active=True,
            )
            class_by_profile, branch_by_profile = _build_roster_context(tenant_id)
            guardian_qs = User.objects.filter(
                tenant_id=tenant_id, role=Role.PARENT, is_active=True,
            )

        class_options = sorted({label for label in class_by_profile.values() if label})

        if class_param == "all":
            class_scope = "all"
        elif class_param:
            class_scope = class_param
        elif request.user.role == Role.SUPER_ADMIN:
            class_scope = class_options[0] if class_options else "all"
        else:
            class_scope = "all"

        students = []
        for u in student_qs.select_related("student_profile", "branch").order_by(
            "first_name", "last_name",
        ):
            profile = getattr(u, "student_profile", None)
            sid = str(profile.id) if profile else str(u.id)
            class_label = class_by_profile.get(sid, "")
            if class_scope != "all" and class_label != class_scope:
                continue
            bid, bname = branch_by_profile.get(
                sid,
                (str(u.branch_id) if u.branch_id else "", u.branch.name if u.branch_id else ""),
            )
            students.append({
                "studentId": sid,
                "studentName": u.full_name,
                "classLabel": class_label,
                "branchId": bid or None,
                "branchName": bname,
            })

        guardians = {str(u.id): u.full_name for u in guardian_qs}
        for link in links:
            guardians.setdefault(str(link.guardian_id), link.guardian.full_name)

        link_rows = []
        for link in links:
            sid = _student_id(link.student)
            class_label = class_by_profile.get(sid, "")
            if class_scope != "all" and class_label != class_scope:
                continue
            bid, bname = branch_by_profile.get(sid, ("", ""))
            link_rows.append(_link(
                link,
                class_label=class_label,
                branch_id=bid or None,
                branch_name=bname,
            ))

        if class_scope != "all":
            guardian_ids = {row["guardianUserId"] for row in link_rows}
            guardians = {uid: name for uid, name in guardians.items() if uid in guardian_ids}

        return Response({
            "links": link_rows,
            "students": students,
            "guardians": [{"userId": uid, "name": name} for uid, name in guardians.items()],
            "branchScope": branch_scope,
            "classScope": class_scope,
            "classOptions": class_options,
        })


class AdminGuardianActionView(APIView):
    """POST { action, payload?/linkId } → save / remove / set-primary a guardian link."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch, _ = resolve_management_scope(request)
        if branch is None:
            return Response(
                {"error": "Select a branch to manage guardian links."},
                status=status.HTTP_400_BAD_REQUEST,
            )
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
