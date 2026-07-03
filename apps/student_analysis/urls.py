"""URL routes for student analysis APIs."""

from django.urls import path

from apps.student_analysis.views.report import StudentReportView

app_name = "student_analysis"

urlpatterns = [
    path("<str:roll_number>/", StudentReportView.as_view(), name="student-report"),
]
