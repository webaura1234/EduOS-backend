"""Faculty self-attendance — monthly summary + daily self check-in."""

import datetime

from rest_framework import status as http
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.hr.queries import staff_attendance as sa_q


def _summary(branch, user) -> dict:
    today = datetime.date.today()
    return {
        "month": today.strftime("%B %Y"),
        "presentDays": sa_q.present_days_in_month(user.pk, today.year, today.month),
        "workingDays": sa_q.working_days_in_month(branch, today.year, today.month),
        "markedToday": sa_q.is_marked(user.pk, today),
    }


class FacultyMyAttendanceView(APIView):
    """GET → monthly present/working summary; POST → self check-in for today."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        return Response(_summary(branch, request.user))

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        sa_q.check_in(branch, request.user)
        return Response(_summary(branch, request.user), status=http.HTTP_201_CREATED)
