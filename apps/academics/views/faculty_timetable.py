"""Faculty-facing weekly timetable + calendar month view."""

import datetime

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.interactors.faculty_timetable import build_faculty_timetable
from apps.academics.scoping import resolve_branch
from apps.attendance.permissions import IsFacultyOrAdmin


class FacultyTimetableView(APIView):
    """GET → FacultyTimetableData for the logged-in faculty.

    Query params: year, month (default current), date (optional day detail).
    """
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        today = datetime.date.today()
        try:
            year = int(request.query_params.get("year", today.year))
            month = int(request.query_params.get("month", today.month))
        except (TypeError, ValueError):
            return Response({"error": "Invalid year or month."}, status=400)
        if month < 1 or month > 12:
            return Response({"error": "Month must be 1–12."}, status=400)

        detail_date = None
        raw_date = request.query_params.get("date")
        if raw_date:
            try:
                detail_date = datetime.date.fromisoformat(raw_date)
            except ValueError:
                return Response({"error": "Invalid date."}, status=400)

        payload = build_faculty_timetable(
            branch=branch,
            user=request.user,
            year=year,
            month=month,
            detail_date=detail_date,
        )
        return Response(payload)
