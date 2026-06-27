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
from apps.attendance.views.student_leave import StudentLeaveView
from apps.attendance.views.faculty_leave import FacultyLeaveReviewView
from apps.attendance.views.faculty_attendance import (
    FacultyAttendanceView,
    FacultyBulkMarkView,
    FacultyLiveAttendanceView,
    FacultyMarkRecordView,
)
from apps.attendance.views.overview import (
    AdminAttendanceLiveView,
    AdminAttendanceOverviewView,
    AdminMarkAttendanceView,
)

app_name = "attendance"

urlpatterns = [
    # Admin aggregate (AttendanceData shape) + polled live snapshot
    path("admin-overview/", AdminAttendanceOverviewView.as_view(), name="admin-overview"),
    path("admin-overview/live/", AdminAttendanceLiveView.as_view(), name="admin-live"),
    path("admin-overview/mark/", AdminMarkAttendanceView.as_view(), name="admin-mark"),

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
    path("me/leave/", StudentLeaveView.as_view(), name="student-leave"),
    path("faculty/leave/", FacultyLeaveReviewView.as_view(), name="faculty-leave-review"),
    path("faculty/attendance/", FacultyAttendanceView.as_view(), name="faculty-attendance"),
    path("faculty/records/<uuid:record_id>/mark/", FacultyMarkRecordView.as_view(),
         name="faculty-mark-record"),
    path("faculty/records/bulk-mark/", FacultyBulkMarkView.as_view(),
         name="faculty-bulk-mark"),
    path("faculty/live/", FacultyLiveAttendanceView.as_view(), name="faculty-live"),
    path("leave/<uuid:leave_id>/", LeaveReviewView.as_view(), name="leave-review"),

    # Student / parent
    path("me/summary/", StudentSummaryView.as_view(), name="student-summary"),
    path("children/<uuid:student_id>/summary/", ChildSummaryView.as_view(), name="child-summary"),
]
