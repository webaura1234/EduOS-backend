"""Student-facing weekly timetable — the logged-in student's own class only."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.models.timetable import DayOfWeek
from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsStudent
from apps.admissions.queries.enrollment import get_active_enrollment_for_profile


def _period(entry) -> dict:
    slot = entry.period_slot
    subject = entry.batch_subject.subject if entry.batch_subject_id else None
    return {
        "subjectName": subject.name if subject else "Subject",
        "startTime": slot.start_time.isoformat() if slot else "",
        "endTime": slot.end_time.isoformat() if slot else "",
        "roomName": entry.room.name if entry.room_id else "—",
        "periodIndex": slot.sequence if slot else 0,
    }


class StudentTimetableView(APIView):
    """GET → { days: [{ dayOfWeek, label, periods: [...] }] } for the student's batch."""
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        profile = getattr(request.user, "student_profile", None)
        enrollment = get_active_enrollment_for_profile(profile.pk) if profile else None
        batch_id = enrollment.batch_id if enrollment else None
        if not batch_id:
            return Response({"days": []})

        # Only this student's batch — entries for any other class are never included.
        by_day: dict = {}
        for e in tt_q.list_active_entries_for_branch(branch.pk):
            if e.timetable.batch_id != batch_id:
                continue
            by_day.setdefault(e.day_of_week, []).append(e)

        days = []
        for day in sorted(by_day.keys()):
            periods = sorted(by_day[day], key=lambda x: (x.period_slot.sequence if x.period_slot_id else 0))
            days.append({
                "dayOfWeek": day,
                "label": DayOfWeek(day).label,
                "periods": [_period(e) for e in periods],
            })
        return Response({"days": days})
