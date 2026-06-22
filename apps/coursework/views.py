"""Homework views — faculty list/assign, student feed."""

import datetime

from rest_framework import status as http
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import structure as struct_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsStudent
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.coursework import queries as hw_q


def _entry(h) -> dict:
    return {
        "id": str(h.id),
        "classSectionId": str(h.batch_id),
        "classLabel": h.batch.name if h.batch_id else "",
        "date": h.date.isoformat(),
        "title": h.title,
        "details": h.details,
        "status": h.status,
        "createdBy": h.created_by.full_name if h.created_by_id else "",
        "createdAt": h.created_at.isoformat(),
        "publishedAt": h.published_at.isoformat() if h.published_at else None,
    }


class FacultyHomeworkView(APIView):
    """GET → FacultyHomeworkData; POST → create/update homework."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        view_scope = "college" if branch.tenant.institution_type == "college" else "school"
        classes = [
            {"id": str(b.id), "label": b.name} for b in struct_q.list_batches(branch.pk)
        ]
        homework = [_entry(h) for h in hw_q.list_for_faculty(branch.pk, request.user.pk)]
        return Response({
            "institutionType": branch.tenant.institution_type,
            "viewScope": view_scope,
            "canAssign": True,
            "classes": classes,
            "homework": homework,
        })

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        title = (request.data.get("title") or "").strip()
        class_section_id = request.data.get("classSectionId")
        if not title or not class_section_id:
            raise ValidationError({"title": "Title and class are required."})
        batch = struct_q.get_batch(branch.pk, class_section_id)
        if batch is None:
            raise ValidationError({"classSectionId": "Class not found."})

        try:
            date = datetime.date.fromisoformat(request.data.get("date"))
        except (TypeError, ValueError):
            date = datetime.date.today()
        publish = bool(request.data.get("publish"))
        details = request.data.get("details", "")

        hw_id = request.data.get("id")
        if hw_id:
            hw = hw_q.get_in_branch(branch.pk, hw_id)
            if hw is None:
                return Response({"error": "Homework not found."}, status=http.HTTP_404_NOT_FOUND)
            hw_q.update(hw, batch=batch, date=date, title=title, details=details,
                        publish=publish, user=request.user)
        else:
            hw = hw_q.create(branch=branch, batch=batch, date=date, title=title,
                             details=details, publish=publish, user=request.user)
        return Response({"success": True, "entry": _entry(hw)},
                        status=http.HTTP_201_CREATED)


class StudentHomeworkView(APIView):
    """GET → { homework } published for the student's batch."""
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        profile = getattr(request.user, "student_profile", None)
        enrollment = get_active_enrollment_for_profile(profile.pk) if profile else None
        if not enrollment or not enrollment.batch_id:
            return Response({"homework": []})
        rows = hw_q.list_published_for_batch(branch.pk, enrollment.batch_id)
        return Response({"homework": [_entry(h) for h in rows]})
