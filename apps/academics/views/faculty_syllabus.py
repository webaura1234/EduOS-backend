"""Faculty syllabus tracking — per-subject units + completion."""

from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import syllabus as syl_q
from apps.academics.scoping import resolve_branch
from apps.attendance.permissions import IsFacultyOrAdmin


def _unit(u) -> dict:
    return {"id": str(u.id), "title": u.title, "order": u.order}


def _subject_payload(subject, class_labels, units) -> dict:
    completed = [u for u in units if u.is_completed]
    total = len(units)
    percent = round(len(completed) / total * 100) if total else 0
    return {
        "id": str(subject.id),
        "name": subject.name,
        "code": subject.code or "",
        "classLabels": class_labels,
        "syllabusCompletionPercent": percent,
        "syllabusUnits": [_unit(u) for u in units],
        "completedUnitIds": [str(u.id) for u in completed],
    }


class FacultySyllabusView(APIView):
    """GET → FacultySyllabusProgressData; PATCH → update one subject's completion."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        subjects = syl_q.faculty_subjects(branch.pk, request.user.pk)
        units_map = syl_q.units_by_subject(
            branch.pk, [s["subject"].id for s in subjects],
        )
        payload = [
            _subject_payload(s["subject"], s["class_labels"], units_map.get(s["subject"].id, []))
            for s in subjects
        ]
        return Response({"subjects": payload})

    def patch(self, request) -> Response:
        branch = resolve_branch(request)
        subject_id = request.data.get("subjectId")
        if not subject_id:
            raise ValidationError({"subjectId": "subjectId is required."})
        completed_ids = request.data.get("completedUnitIds", [])
        units = syl_q.set_completion(branch.pk, subject_id, completed_ids, user=request.user)

        # Re-resolve class labels for the affected subject so the response matches the GET shape.
        labels = next(
            (s["class_labels"] for s in syl_q.faculty_subjects(branch.pk, request.user.pk)
             if str(s["subject"].id) == str(subject_id)),
            [],
        )
        subject = units[0].subject if units else None
        if subject is None:
            return Response({"subject": None})
        return Response({"subject": _subject_payload(subject, labels, units)})
