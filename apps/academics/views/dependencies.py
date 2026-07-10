"""Dependency counts before deleting academics entities."""

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models import TimetableEntry, TimetableEntryStatus
from apps.academics.queries import calendar as cal_q
from apps.academics.queries import curriculum as curr_q
from apps.academics.queries import structure as struct_q
from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin


class AcademicsDependenciesView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        entity_type = request.query_params.get("entityType", "")
        entity_id = request.query_params.get("entityId", "")
        if not entity_type or not entity_id:
            return Response(
                {"error": "entityType and entityId are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        deps: dict[str, int] = {}

        if entity_type == "class_section":
            batch = struct_q.get_batch(branch.pk, entity_id)
            if batch is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            deps["timetable"] = TimetableEntry.objects.filter(
                timetable__batch_id=batch.pk, is_active=True,
            ).count()
            deps["studyMaterials"] = struct_q.batch_has_study_materials(batch.pk) and 1 or 0
            deps["students"] = struct_q.batch_has_students(batch.pk) and 1 or 0

        elif entity_type == "subject":
            subject = curr_q.get_subject(branch.pk, entity_id)
            if subject is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            deps["timetable"] = TimetableEntry.objects.filter(
                batch_subject__subject_id=subject.pk,
                is_active=True,
                status=TimetableEntryStatus.ACTIVE,
            ).count()
            deps["marks"] = 1 if curr_q.subject_has_marks(subject.pk) else 0

        elif entity_type == "department":
            dept = struct_q.get_department(branch.pk, entity_id)
            if dept is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            deps["courses"] = struct_q.list_courses(branch.pk, department_id=dept.pk).count()

        elif entity_type == "period":
            period = cal_q.get_period_for_branch(branch.pk, entity_id)
            if period is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            from apps.academics.models import BatchSubject, Timetable

            deps["batchSubjects"] = BatchSubject.objects.filter(
                academic_period_id=period.pk, is_active=True,
            ).count()
            deps["timetables"] = Timetable.objects.filter(
                academic_period_id=period.pk, is_active=True,
            ).count()

        elif entity_type == "room":
            room = tt_q.get_room(branch.pk, entity_id)
            if room is None:
                return Response({"error": "Not found."}, status=status.HTTP_404_NOT_FOUND)
            deps["timetable"] = TimetableEntry.objects.filter(
                room_id=room.pk, is_active=True,
            ).count()

        else:
            return Response(
                {"error": f"Unsupported entityType: {entity_type}"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"dependencies": deps})
