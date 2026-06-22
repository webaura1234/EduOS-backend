"""Syllabus unit authoring — list/create/update/delete units for a subject.

Open to faculty and admins so a teacher can lay out their own subject's syllabus.
"""

from rest_framework import status as http
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import syllabus as syl_q
from apps.academics.scoping import resolve_branch
from apps.attendance.permissions import IsFacultyOrAdmin


def _unit(u) -> dict:
    return {
        "id": str(u.id),
        "subjectId": str(u.subject_id),
        "title": u.title,
        "order": u.order,
        "isCompleted": u.is_completed,
    }


class SyllabusUnitListCreateView(APIView):
    """GET ?subjectId= → units; POST {subjectId, title, order?} → create."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        subject_id = request.query_params.get("subjectId")
        if not subject_id:
            raise ValidationError({"subjectId": "subjectId is required."})
        units = syl_q.units_for_subject(branch.pk, subject_id)
        return Response({"units": [_unit(u) for u in units]})

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        subject_id = request.data.get("subjectId")
        title = (request.data.get("title") or "").strip()
        if not subject_id or not title:
            raise ValidationError({"title": "subjectId and title are required."})
        subject = curr_q.get_subject(branch.pk, subject_id)
        if subject is None:
            return Response({"error": "Subject not found."}, status=http.HTTP_404_NOT_FOUND)
        order = request.data.get("order")
        unit = syl_q.create_unit(
            branch=branch, subject=subject, title=title,
            order=int(order) if order is not None else None, user=request.user,
        )
        return Response({"unit": _unit(unit)}, status=http.HTTP_201_CREATED)


class SyllabusUnitDetailView(APIView):
    """PATCH {title?, order?} → update; DELETE → soft-delete."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def patch(self, request, unit_id) -> Response:
        branch = resolve_branch(request)
        unit = syl_q.get_unit(branch.pk, unit_id)
        if unit is None:
            return Response({"error": "Unit not found."}, status=http.HTTP_404_NOT_FOUND)
        title = request.data.get("title")
        order = request.data.get("order")
        unit = syl_q.update_unit(
            unit,
            title=title.strip() if isinstance(title, str) else None,
            order=int(order) if order is not None else None,
            user=request.user,
        )
        return Response({"unit": _unit(unit)})

    def delete(self, request, unit_id) -> Response:
        branch = resolve_branch(request)
        unit = syl_q.get_unit(branch.pk, unit_id)
        if unit is None:
            return Response({"error": "Unit not found."}, status=http.HTTP_404_NOT_FOUND)
        syl_q.delete_unit(unit, user=request.user)
        return Response({"success": True}, status=http.HTTP_200_OK)
