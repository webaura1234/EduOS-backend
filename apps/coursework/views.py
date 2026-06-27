"""Homework views — faculty list/assign, student feed."""

import datetime

from rest_framework import status as http
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import faculty_teaching as ft_q
from apps.academics.queries import structure as struct_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsStudent
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.coursework import queries as hw_q


def _batch_label(batch) -> str:
    if batch and batch.course_id:
        return f"{batch.course.name} - {batch.name}"
    return batch.name if batch else ""


def _entry(h) -> dict:
    return {
        "id": str(h.id),
        "classSectionId": str(h.batch_id),
        "classLabel": _batch_label(h.batch) if h.batch_id else "",
        "date": h.date.isoformat(),
        "title": h.title,
        "details": h.details,
        "status": h.status,
        "createdBy": h.created_by.full_name if h.created_by_id else "",
        "createdByUserId": str(h.created_by_id) if h.created_by_id else None,
        "createdAt": h.created_at.isoformat(),
        "publishedAt": h.published_at.isoformat() if h.published_at else None,
    }


def _can_manage_homework(branch_id, user, hw) -> bool:
    if user.role in ("admin", "super_admin"):
        return True
    if hw.created_by_id == user.pk:
        return True
    return ft_q.is_homeroom_teacher(branch_id, user.pk, hw.batch_id)


class FacultyHomeworkView(APIView):
    """GET → FacultyHomeworkData; POST → create/update homework."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        view_scope = "college" if branch.tenant.institution_type == "college" else "school"
        faculty_id = request.user.pk

        homerooms = ft_q.homeroom_batches(branch.pk, faculty_id)
        homeroom_ids = [b.id for b in homerooms]
        teaching_batch_ids = ft_q.subject_teaching_batch_ids(branch.pk, faculty_id)

        my_class_hw = [_entry(h) for h in hw_q.list_for_batches(branch.pk, homeroom_ids)]
        other_hw = [
            _entry(h)
            for h in hw_q.list_for_faculty_in_batches(branch.pk, faculty_id, list(teaching_batch_ids))
        ]

        return Response({
            "institutionType": branch.tenant.institution_type,
            "viewScope": view_scope,
            "facultyUserId": str(faculty_id),
            "canAssign": len(teaching_batch_ids) > 0,
            "myClass": {
                "homerooms": ft_q.homerooms_payload(homerooms),
                "homework": my_class_hw,
            },
            "otherClasses": {
                "teachingClasses": ft_q.teaching_classes_grouped(branch.pk, faculty_id),
                "homework": other_hw,
            },
        })

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        faculty_id = request.user.pk
        title = (request.data.get("title") or "").strip()
        class_section_id = request.data.get("classSectionId")
        if not title or not class_section_id:
            raise ValidationError({"title": "Title and class are required."})
        batch = struct_q.get_batch(branch.pk, class_section_id)
        if batch is None:
            raise ValidationError({"classSectionId": "Class not found."})

        teaching_batch_ids = ft_q.subject_teaching_batch_ids(branch.pk, faculty_id)
        if batch.id not in teaching_batch_ids:
            raise PermissionDenied(
                "You can only post homework for classes where you are assigned as a subject teacher."
            )

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
            if not _can_manage_homework(branch.pk, request.user, hw):
                raise PermissionDenied("You cannot edit this homework.")
            hw_q.update(hw, batch=batch, date=date, title=title, details=details,
                        publish=publish, user=request.user)
        else:
            hw = hw_q.create(branch=branch, batch=batch, date=date, title=title,
                             details=details, publish=publish, user=request.user)
        return Response({"success": True, "entry": _entry(hw)},
                        status=http.HTTP_201_CREATED)


class FacultyHomeworkDetailView(APIView):
    """DELETE a homework item. Author, homeroom teacher, or admin may delete."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def delete(self, request, homework_id) -> Response:
        branch = resolve_branch(request)
        hw = hw_q.get_in_branch(branch.pk, homework_id)
        if hw is None:
            return Response({"error": "Homework not found."}, status=http.HTTP_404_NOT_FOUND)
        if not _can_manage_homework(branch.pk, request.user, hw):
            return Response({"error": "You cannot delete this homework."},
                            status=http.HTTP_403_FORBIDDEN)
        hw_q.soft_delete(hw, user=request.user)
        return Response({"success": True})


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
