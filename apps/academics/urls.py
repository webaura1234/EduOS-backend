"""
URL configuration for the academics app.

Mounted at /api/v1/academics/ (see config/urls.py).
"""

from django.urls import path

from apps.academics.views.calendar import (
    AcademicPeriodDetailView,
    AcademicPeriodListCreateView,
    AcademicYearActionsView,
    AcademicYearDetailView,
    AcademicYearListCreateView,
)
from apps.academics.views.curriculum import (
    BatchFacultyDetailView,
    BatchFacultyListCreateView,
    BatchSubjectDetailView,
    BatchSubjectListCreateView,
    SubjectArchiveView,
    SubjectDetailView,
    SubjectListCreateView,
)
from apps.academics.views.holiday import HolidayDetailView, HolidayListCreateView
from apps.academics.views.rollover import (
    RolloverExecuteView,
    RolloverPreviewView,
    RolloverStatusView,
    RolloverUndoView,
)
from apps.academics.views.structure import (
    BatchDetailView,
    BatchListCreateView,
    CourseDetailView,
    CourseListCreateView,
    DepartmentDetailView,
    DepartmentListCreateView,
)
from apps.academics.views.timetable import (
    PeriodSlotDetailView,
    PeriodSlotListCreateView,
    RoomDetailView,
    RoomListCreateView,
    TimetableActionsView,
    TimetableClashesView,
    TimetableDetailView,
    TimetableEntryDetailView,
    TimetableEntryListCreateView,
    TimetableListView,
)

app_name = "academics"

urlpatterns = [
    # Calendar
    path("academic-years/", AcademicYearListCreateView.as_view(), name="academic-years"),
    path("academic-years/actions/", AcademicYearActionsView.as_view(), name="academic-year-actions"),
    path("academic-years/<uuid:year_id>/", AcademicYearDetailView.as_view(), name="academic-year-detail"),
    path(
        "academic-years/<uuid:year_id>/periods/",
        AcademicPeriodListCreateView.as_view(),
        name="academic-periods",
    ),
    path(
        "academic-years/<uuid:year_id>/periods/<uuid:period_id>/",
        AcademicPeriodDetailView.as_view(),
        name="academic-period-detail",
    ),
    # Structure
    path("departments/", DepartmentListCreateView.as_view(), name="departments"),
    path("departments/<uuid:dept_id>/", DepartmentDetailView.as_view(), name="department-detail"),
    path("courses/", CourseListCreateView.as_view(), name="courses"),
    path("courses/<uuid:course_id>/", CourseDetailView.as_view(), name="course-detail"),
    path("batches/", BatchListCreateView.as_view(), name="batches"),
    path("batches/<uuid:batch_id>/", BatchDetailView.as_view(), name="batch-detail"),
    # Curriculum
    path("subjects/", SubjectListCreateView.as_view(), name="subjects"),
    path("subjects/<uuid:subject_id>/", SubjectDetailView.as_view(), name="subject-detail"),
    path("subjects/<uuid:subject_id>/archive/", SubjectArchiveView.as_view(), name="subject-archive"),
    path("batch-subjects/", BatchSubjectListCreateView.as_view(), name="batch-subjects"),
    path("batch-subjects/<uuid:batch_subject_id>/", BatchSubjectDetailView.as_view(), name="batch-subject-detail"),
    path("batch-faculty/", BatchFacultyListCreateView.as_view(), name="batch-faculty"),
    path("batch-faculty/<uuid:assignment_id>/", BatchFacultyDetailView.as_view(), name="batch-faculty-detail"),
    # Timetable infrastructure
    path("period-slots/", PeriodSlotListCreateView.as_view(), name="period-slots"),
    path("period-slots/<uuid:slot_id>/", PeriodSlotDetailView.as_view(), name="period-slot-detail"),
    path("rooms/", RoomListCreateView.as_view(), name="rooms"),
    path("rooms/<uuid:room_id>/", RoomDetailView.as_view(), name="room-detail"),
    # Timetable
    path("timetables/", TimetableListView.as_view(), name="timetables"),
    path("timetables/clashes/", TimetableClashesView.as_view(), name="timetable-clashes"),
    path("timetables/actions/", TimetableActionsView.as_view(), name="timetable-actions"),
    path("timetables/<uuid:timetable_id>/", TimetableDetailView.as_view(), name="timetable-detail"),
    path(
        "timetables/<uuid:timetable_id>/entries/",
        TimetableEntryListCreateView.as_view(),
        name="timetable-entries",
    ),
    path(
        "timetables/entries/<uuid:entry_id>/",
        TimetableEntryDetailView.as_view(),
        name="timetable-entry-detail",
    ),
    # Holidays
    path("holidays/", HolidayListCreateView.as_view(), name="holidays"),
    path("holidays/<uuid:holiday_id>/", HolidayDetailView.as_view(), name="holiday-detail"),
    # Rollover
    path("rollover/preview/", RolloverPreviewView.as_view(), name="rollover-preview"),
    path("rollover/execute/", RolloverExecuteView.as_view(), name="rollover-execute"),
    path("rollover/undo/", RolloverUndoView.as_view(), name="rollover-undo"),
    path("rollover/status/", RolloverStatusView.as_view(), name="rollover-status"),
]
