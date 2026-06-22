"""Faculty dashboard — today's classes, pending reviews, announcements, holidays."""

import datetime

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.queries import holiday as hol_q
from apps.academics.queries import timetable as tt_q
from apps.academics.scoping import resolve_branch
from apps.attendance.permissions import IsFacultyOrAdmin
from apps.attendance.queries import leave as att_leave_q
from apps.communications.queries import announcement as ann_q
from apps.communications.views.announcement import _announcement

_QUICK_ACTIONS = [
    {"id": "mark-attendance", "label": "Mark attendance",
     "description": "Record today's class attendance", "href": "/faculty/attendance",
     "variant": "primary"},
    {"id": "apply-leave", "label": "Apply for leave",
     "description": "Submit a leave request", "href": "/faculty/my-leave",
     "variant": "secondary"},
    {"id": "payslip", "label": "View payslip",
     "description": "Download your latest payslip", "href": "/faculty/payslip",
     "variant": "secondary"},
]


def _slot(e) -> dict:
    slot = e.period_slot
    has_subject = e.batch_subject_id is not None
    subject = e.batch_subject.subject if has_subject else None
    return {
        "id": str(e.id),
        "classSectionId": str(e.timetable.batch_id),
        "subjectId": str(subject.id) if subject else "",
        "facultyUserId": str(e.faculty_id) if e.faculty_id else "",
        "roomId": str(e.room_id) if e.room_id else "",
        "dayOfWeek": e.day_of_week,
        "periodIndex": slot.sequence if slot else 0,
        "startTime": slot.start_time.isoformat() if slot else "",
        "endTime": slot.end_time.isoformat() if slot else "",
        "status": "active",
        "statusNote": None,
        "classLabel": e.timetable.batch.name,
        "subjectName": subject.name if subject else "Subject",
    }


def _holiday(h) -> dict:
    applies = h.applies_to or {}
    is_all = applies.get("all") is True or not applies.get("batchIds")
    return {
        "id": str(h.id),
        "name": h.name,
        "date": h.date.isoformat(),
        "scope": "institution" if is_all else "classes",
        "classIds": applies.get("batchIds", []),
        "blocksAttendance": True,
        "createdAt": "",
    }


class FacultyDashboardView(APIView):
    """GET → FacultyDashboardData for the logged-in faculty."""
    permission_classes = [IsAuthenticated, IsFacultyOrAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        user = request.user
        today = datetime.date.today()
        weekday = today.isoweekday()

        # Today's classes for this faculty
        try:
            schedule = [
                _slot(e)
                for e in tt_q.list_active_entries_for_branch(branch.pk)
                if e.faculty_id == user.pk and e.day_of_week == weekday
            ]
        except Exception:
            schedule = []

        # Pending student leave reviews
        try:
            pending_leave = att_leave_q.list_leaves(branch.pk, status="pending").count()
        except Exception:
            pending_leave = 0

        # Announcements + holidays
        try:
            announcements = [_announcement(a) for a in ann_q.list_for_faculty(branch.pk)[:5]]
        except Exception:
            announcements = []
        try:
            holidays = [
                _holiday(h) for h in hol_q.list_holidays(branch.pk, from_date=today)[:5]
            ]
        except Exception:
            holidays = []

        sessions_today = len(schedule)
        alerts = []
        if pending_leave > 0:
            alerts.append({
                "id": "leave-pending", "title": "Leave requests pending",
                "message": "Students awaiting your approval on leave applications.",
                "severity": "warning", "href": "/faculty/leave", "count": pending_leave,
            })
        if sessions_today > 0:
            alerts.append({
                "id": "attendance-unmarked", "title": "Classes scheduled today",
                "message": "Mark attendance for today's sessions before end of day.",
                "severity": "info", "href": "/faculty/attendance", "count": sessions_today,
            })

        return Response({
            "today": today.isoformat(),
            "schedule": schedule,
            "snapshot": {
                "sessionsToday": sessions_today,
                "sessionsCompleted": 0,
                "pendingLeave": pending_leave,
                "announcementsCount": len(announcements),
                "attendanceMarkedPercent": 0,
                "syllabusProgressPercent": 0,
            },
            "quickActions": _QUICK_ACTIONS,
            "alerts": alerts,
            "cards": [],  # deprecated
            "announcements": announcements,
            "upcomingHolidays": holidays,
        })
