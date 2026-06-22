"""Faculty-facing study materials (Notes) — list own uploads + the slots to upload against."""

import datetime

from rest_framework import status as http
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models.timetable import DayOfWeek
from apps.academics.queries import admin_extras as extra_q
from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.attendance.permissions import IsFacultyOrAdmin


def _material(m) -> dict:
    bs = m.timetable_entry.batch_subject if m.timetable_entry_id else None
    return {
        "id": str(m.id),
        "timetableSlotId": str(m.timetable_entry_id),
        "sessionDate": m.session_date.isoformat(),
        "fileName": m.file_name,
        "s3Key": m.s3_key,
        "url": m.url,
        "uploadedAt": m.created_at.isoformat(),
        "uploadedByUserId": str(m.uploaded_by_id) if m.uploaded_by_id else "",
    }


def _upload_session(e) -> dict:
    subject = e.batch_subject.subject.name if e.batch_subject_id else "Subject"
    class_label = e.timetable.batch.name if e.timetable_id and e.timetable.batch_id else ""
    day_label = DayOfWeek(e.day_of_week).label
    period_index = e.period_slot.sequence if e.period_slot_id else 0
    return {
        "timetableSlotId": str(e.id),
        "label": f"{subject} · {day_label} P{period_index}",
        "classLabel": class_label,
        "subjectName": subject,
        "dayOfWeek": e.day_of_week,
        "periodIndex": period_index,
    }


class FacultyStudyMaterialsView(APIView):
    """GET → FacultyNotesData; POST → record an uploaded study material."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        materials = extra_q.list_materials_for_faculty(branch.pk, request.user.pk)
        slots = tt_q.list_faculty_teaching_slots(branch.pk, request.user.pk)
        return Response({
            "materials": [_material(m) for m in materials],
            "uploadSessions": [_upload_session(e) for e in slots],
        })

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        slot_id = request.data.get("timetableSlotId")
        file_name = (request.data.get("fileName") or "").strip()
        if not slot_id or not file_name:
            raise ValidationError({"fileName": "Timetable slot and file name are required."})

        entry = tt_q.get_timetable_entry(branch.pk, slot_id)
        if entry is None:
            return Response({"error": "Timetable slot not found."},
                            status=http.HTTP_404_NOT_FOUND)
        try:
            session_date = datetime.date.fromisoformat(request.data.get("sessionDate"))
        except (TypeError, ValueError):
            session_date = datetime.date.today()

        material = extra_q.create_study_material(
            branch=branch, timetable_entry=entry, session_date=session_date,
            file_name=file_name,
            s3_key=request.data.get("s3Key", ""), url=request.data.get("url", ""),
            user=request.user,
        )
        return Response(_material(material), status=http.HTTP_201_CREATED)
