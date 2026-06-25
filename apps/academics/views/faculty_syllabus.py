"""Faculty syllabus tracking — per (batch, subject) units + section-scoped completion."""

from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.helpers import batch_display_label
from apps.academics.queries import syllabus as syl_q
from apps.academics.scoping import resolve_branch
from apps.accounts.models.user import Role
from apps.attendance.permissions import IsFacultyOrAdmin


class FacultySyllabusView(APIView):
    """GET → FacultySyllabusProgressData; PATCH → update one section's completion."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        assignments = syl_q.faculty_assignments(branch.pk, request.user.pk)
        subject_ids = list({a["subject"].id for a in assignments})
        units_map = syl_q.units_by_subject(branch.pk, subject_ids)
        payload = []
        for a in assignments:
            subject = a["subject"]
            batch = a["batch"]
            units = units_map.get(subject.id, [])
            completed = syl_q.completed_ids_for_batch(branch.pk, batch.pk, subject.pk)
            payload.append(syl_q.payload_for_assignment(
                subject=subject,
                batch=batch,
                units=units,
                completed_ids=completed,
                class_label=batch_display_label(batch),
            ))
        return Response({"subjects": payload})

    def patch(self, request) -> Response:
        branch = resolve_branch(request)
        subject_id = request.data.get("subjectId")
        batch_id = request.data.get("batchId")
        if not subject_id:
            raise ValidationError({"subjectId": "subjectId is required."})
        if not batch_id:
            raise ValidationError({"batchId": "batchId is required."})

        user = request.user
        if user.role == Role.FACULTY and not syl_q.faculty_teaches(
            branch.pk, user.pk, batch_id, subject_id,
        ):
            raise PermissionDenied("You are not assigned to teach this subject in this class.")

        completed_ids = request.data.get("completedUnitIds", [])
        try:
            units = syl_q.set_completion(
                branch.pk, batch_id, subject_id, completed_ids, user=user,
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc

        from apps.academics.queries import curriculum as curr_q
        subject = curr_q.get_subject(branch.pk, subject_id)
        from apps.academics.queries import structure as struct_q
        batch = struct_q.get_batch(branch.pk, batch_id)
        if subject is None or batch is None:
            return Response({"subject": None})
        done = syl_q.completed_ids_for_batch(branch.pk, batch_id, subject_id)
        return Response({"subject": syl_q.payload_for_assignment(
            subject=subject,
            batch=batch,
            units=units,
            completed_ids=done,
            class_label=batch_display_label(batch),
        )})
