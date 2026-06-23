"""Faculty invigilation duties — read-only list of the logged-in faculty's assignments."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.examinations.queries import invigilator as inv_q


def _assignment(duty) -> dict:
    slot = duty.schedule_slot
    exam = slot.exam
    return {
        "examSlotId": str(duty.schedule_slot_id),
        "slotLabel": f"{exam.name} — {slot.subject.name} ({slot.batch.name})",
        "facultyId": str(duty.faculty_id),
        "facultyName": duty.faculty.full_name if duty.faculty_id else "",
        "assignedAt": duty.created_at.isoformat(),
        "assignedBy": "manual",
    }


class FacultyInvigilationView(APIView):
    """GET → FacultyInvigilationData for the logged-in faculty."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        duties = inv_q.list_for_faculty(branch.pk, request.user.pk)
        return Response({"assignments": [_assignment(d) for d in duties]})
