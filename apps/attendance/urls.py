"""URL configuration for the attendance app (mounted at /api/v1/attendance/)."""

from django.urls import path

from apps.attendance.views.attendance import (
    ChildSummaryView,
    CorrectRecordView,
    DetentionReportView,
    FlaggedQueueView,
    LiveBoardView,
    MonthlyReportView,
    SessionDetailView,
    SessionMarkView,
    SessionOpenView,
    SessionRosterView,
    ShortageReportView,
    StudentSummaryView,
)
from apps.attendance.views.leave import AuditLogView, LeaveListCreateView, LeaveReviewView
from apps.attendance.views.overview import (
    AdminAttendanceLiveView,
    AdminAttendanceOverviewView,
)

app_name = "attendance"

urlpatterns = [
    # Admin aggregate (AttendanceData shape) + polled live snapshot
    path("admin-overview/", AdminAttendanceOverviewView.as_view(), name="admin-overview"),
    path("admin-overview/live/", AdminAttendanceLiveView.as_view(), name="admin-live"),

    # Marking (faculty/admin)
    path("sessions/", SessionOpenView.as_view(), name="session-open"),
    path("sessions/<uuid:session_id>/", SessionDetailView.as_view(), name="session-detail"),
    path("sessions/<uuid:session_id>/roster/", SessionRosterView.as_view(), name="session-roster"),
    path("sessions/<uuid:session_id>/mark/", SessionMarkView.as_view(), name="session-mark"),

    # Admin live board
    path("live/", LiveBoardView.as_view(), name="live"),

    # Reports
    path("reports/shortage/", ShortageReportView.as_view(), name="report-shortage"),
    path("reports/detention/", DetentionReportView.as_view(), name="report-detention"),
    path("reports/monthly/", MonthlyReportView.as_view(), name="report-monthly"),

    # Corrections / audit / flagged
    path("records/<uuid:record_id>/correct/", CorrectRecordView.as_view(), name="record-correct"),
    path("audit/", AuditLogView.as_view(), name="audit"),
    path("flagged/", FlaggedQueueView.as_view(), name="flagged"),

    # Leave workflow
    path("leave/", LeaveListCreateView.as_view(), name="leave"),
    path("leave/<uuid:leave_id>/", LeaveReviewView.as_view(), name="leave-review"),

    # Student / parent
    path("me/summary/", StudentSummaryView.as_view(), name="student-summary"),
    path("children/<uuid:student_id>/summary/", ChildSummaryView.as_view(), name="child-summary"),
]
