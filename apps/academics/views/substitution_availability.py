"""GET available substitute faculty for a timetable session on a date."""

import datetime

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import substitution_availability as avail_q
from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin


class SubstitutionAvailableFacultyView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        slot_id = request.query_params.get("timetableSlotId")
        raw_date = request.query_params.get("date")
        if not slot_id or not raw_date:
            return Response(
                {"error": "timetableSlotId and date are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            on_date = datetime.date.fromisoformat(raw_date)
        except ValueError:
            return Response({"error": "Invalid date."}, status=status.HTTP_400_BAD_REQUEST)

        entry = tt_q.get_timetable_entry(branch.pk, slot_id)
        if entry is None:
            return Response({"error": "Timetable slot not found."}, status=status.HTTP_404_NOT_FOUND)

        if entry.day_of_week != on_date.weekday():
            return Response(
                {"error": "Selected date does not match this session's weekday."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = avail_q.available_substitute_faculty(
            branch=branch,
            timetable_entry=entry,
            on_date=on_date,
        )
        return Response(payload)
