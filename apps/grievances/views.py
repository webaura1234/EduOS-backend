"""Grievance views — student raise/list, admin inbox + assign/resolve."""

from rest_framework import status as http
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin, IsStudent
from apps.grievances import queries as g_q


def _class_label(student_user) -> str:
    profile = getattr(student_user, "student_profile", None)
    batch = getattr(profile, "current_batch", None) if profile else None
    return batch.name if batch else ""


def _grievance(g) -> dict:
    return {
        "id": str(g.id),
        "category": g.category,
        "subject": g.subject,
        "description": g.description,
        "status": g.status,
        "createdAt": g.created_at.isoformat(),
        "updatedAt": g.updated_at.isoformat(),
        "resolutionNote": g.resolution_note or None,
        "raisedByRole": g.raised_by_role,
        "raisedByName": g.raised_by.full_name if g.raised_by_id else "",
        "assignedToId": str(g.assigned_to_id) if g.assigned_to_id else None,
        "assignedToName": g.assigned_to.full_name if g.assigned_to_id else None,
        "assignedAt": g.assigned_at.isoformat() if g.assigned_at else None,
    }


def _admin_row(g) -> dict:
    row = _grievance(g)
    row.update({
        "raisedById": str(g.raised_by_id),
        "raisedByName": g.raised_by.full_name if g.raised_by_id else "",
        "classLabel": _class_label(g.student),
    })
    return row


class StudentGrievancesView(APIView):
    """GET → { grievances } (own); POST { category, subject, description } → raise one."""
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        rows = g_q.list_for_raiser(branch.pk, request.user.pk)
        return Response({"grievances": [_grievance(g) for g in rows]})

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        subject = (request.data.get("subject") or "").strip()
        category = (request.data.get("category") or "").strip()
        if not subject or not category:
            raise ValidationError({"subject": "Category and subject are required."})

        grievance = g_q.create_grievance(
            branch=branch, raised_by=request.user, raised_by_role="student",
            student=request.user, category=category, subject=subject,
            description=request.data.get("description", ""), user=request.user,
        )
        return Response({"grievance": _grievance(grievance)}, status=http.HTTP_201_CREATED)


class AdminGrievancesView(APIView):
    """GET → { grievances } across the branch (admin inbox)."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        rows = g_q.list_for_branch(branch.pk, status=request.query_params.get("status"))
        return Response({"grievances": [_admin_row(g) for g in rows]})


class AdminGrievanceActionView(APIView):
    """POST { action, grievanceId, ... } → assign / resolve."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        action = request.data.get("action")
        grievance = g_q.get_in_branch(branch.pk, request.data.get("grievanceId"))
        if grievance is None:
            return Response({"error": "Grievance not found."}, status=http.HTTP_404_NOT_FOUND)

        if action == "assign":
            g_q.assign(grievance, request.data.get("assigneeId"), user=request.user)
            return Response({"grievance": _admin_row(grievance)})
        if action == "resolve":
            g_q.resolve(
                grievance, resolution_note=request.data.get("resolutionNote", ""),
                status=request.data.get("status", "resolved"), user=request.user,
            )
            return Response({"grievance": _admin_row(grievance)})
        if action == "reopen":
            g_q.reopen(grievance, user=request.user)
            return Response({"grievance": _admin_row(grievance)})

        return Response({"error": "Unknown action."}, status=http.HTTP_400_BAD_REQUEST)
