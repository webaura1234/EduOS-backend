"""
URL configuration for the examinations app.

Mounted at /api/v1/examinations/ (see config/urls.py).
"""

from django.urls import path

from apps.examinations.views.assignment import (
    AssignmentListCreateView,
    AssignmentSubmitView,
    SubmissionGradeView,
)
from apps.examinations.views.hub import (
    ParentChildAssignmentsHubView,
    ParentChildExamHubView,
    ParentChildResultsHubView,
    StudentAssignmentsHubView,
    StudentExamHubView,
    StudentPerformanceHubView,
    StudentResultsHubView,
)
from apps.examinations.views.exam import (
    ExamDetailView,
    ExamListCreateView,
    ExamScheduleDetailView,
    ExamScheduleListCreateView,
    GradeScaleDetailView,
    GradeScaleListCreateView,
)
from apps.examinations.views.logistics import ExamInvigilatorView, ExamSeatingGenerateView
from apps.examinations.views.marks import (
    MarksEntryDetailView,
    ScheduleSlotMarksSubmitView,
    ScheduleSlotMarksView,
    ScheduleSlotRosterView,
)
from apps.examinations.views.registration import ExamRegistrationListCreateView, HallTicketView
from apps.examinations.views.result import (
    ExamAnalyticsView,
    ExamGraceMarksView,
    ExamResultsComputeView,
    ExamResultsPublishView,
    ExamResultsReviseView,
)
from apps.examinations.views.internal import (
    FacultyInternalMarkSaveView,
    FacultyMarksView,
)
from apps.examinations.views.invigilation import FacultyInvigilationView

app_name = "examinations"

urlpatterns = [
    path("grade-scales/", GradeScaleListCreateView.as_view(), name="grade-scale-list"),
    path("grade-scales/<uuid:scale_id>/", GradeScaleDetailView.as_view(), name="grade-scale-detail"),
    path("exams/", ExamListCreateView.as_view(), name="exam-list"),
    path("exams/<uuid:exam_id>/", ExamDetailView.as_view(), name="exam-detail"),
    path("exams/<uuid:exam_id>/schedule/", ExamScheduleListCreateView.as_view(), name="exam-schedule-list"),
    path(
        "exams/<uuid:exam_id>/schedule/<uuid:slot_id>/",
        ExamScheduleDetailView.as_view(),
        name="exam-schedule-detail",
    ),
    path(
        "exams/<uuid:exam_id>/register/",
        ExamRegistrationListCreateView.as_view(),
        name="exam-register",
    ),
    path(
        "registrations/<uuid:registration_id>/hall-ticket/",
        HallTicketView.as_view(),
        name="hall-ticket",
    ),
    path(
        "exams/<uuid:exam_id>/seating/generate/",
        ExamSeatingGenerateView.as_view(),
        name="exam-seating-generate",
    ),
    path(
        "exams/<uuid:exam_id>/invigilators/",
        ExamInvigilatorView.as_view(),
        name="exam-invigilators",
    ),
    path(
        "schedule-slots/<uuid:slot_id>/roster/",
        ScheduleSlotRosterView.as_view(),
        name="schedule-slot-roster",
    ),
    path(
        "schedule-slots/<uuid:slot_id>/marks/",
        ScheduleSlotMarksView.as_view(),
        name="schedule-slot-marks",
    ),
    path(
        "schedule-slots/<uuid:slot_id>/marks/submit/",
        ScheduleSlotMarksSubmitView.as_view(),
        name="schedule-slot-marks-submit",
    ),
    path(
        "marks/<uuid:marks_id>/",
        MarksEntryDetailView.as_view(),
        name="marks-detail",
    ),
    path(
        "exams/<uuid:exam_id>/results/compute/",
        ExamResultsComputeView.as_view(),
        name="exam-results-compute",
    ),
    path(
        "exams/<uuid:exam_id>/results/publish/",
        ExamResultsPublishView.as_view(),
        name="exam-results-publish",
    ),
    path(
        "exams/<uuid:exam_id>/results/revise/",
        ExamResultsReviseView.as_view(),
        name="exam-results-revise",
    ),
    path(
        "exams/<uuid:exam_id>/grace-marks/",
        ExamGraceMarksView.as_view(),
        name="exam-grace-marks",
    ),
    path(
        "exams/<uuid:exam_id>/analytics/",
        ExamAnalyticsView.as_view(),
        name="exam-analytics",
    ),
    path("assignments/", AssignmentListCreateView.as_view(), name="assignment-list"),
    path(
        "assignments/<uuid:assignment_id>/submit/",
        AssignmentSubmitView.as_view(),
        name="assignment-submit",
    ),
    path(
        "submissions/<uuid:submission_id>/grade/",
        SubmissionGradeView.as_view(),
        name="submission-grade",
    ),
    path("me/exams/", StudentExamHubView.as_view(), name="student-exam-hub"),
    path("me/results/", StudentResultsHubView.as_view(), name="student-results-hub"),
    path("me/performance/", StudentPerformanceHubView.as_view(), name="student-performance-hub"),
    path("me/assignments/", StudentAssignmentsHubView.as_view(), name="student-assignments-hub"),
    path("me/marks/", FacultyMarksView.as_view(), name="faculty-marks"),
    path("me/internal-marks/", FacultyInternalMarkSaveView.as_view(), name="faculty-internal-marks-save"),
    path("me/invigilation/", FacultyInvigilationView.as_view(), name="faculty-invigilation"),
    path(
        "children/<uuid:student_id>/exams/",
        ParentChildExamHubView.as_view(),
        name="parent-child-exam-hub",
    ),
    path(
        "children/<uuid:student_id>/results/",
        ParentChildResultsHubView.as_view(),
        name="parent-child-results-hub",
    ),
    path(
        "children/<uuid:student_id>/assignments/",
        ParentChildAssignmentsHubView.as_view(),
        name="parent-child-assignments-hub",
    ),
]
