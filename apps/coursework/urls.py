from django.urls import path

from apps.coursework.views import (
    FacultyHomeworkDetailView,
    FacultyHomeworkView,
    StudentHomeworkView,
)
from apps.coursework.views_admin_school import AdminSchoolOverviewView

app_name = "coursework"

urlpatterns = [
    path("admin/school-overview/", AdminSchoolOverviewView.as_view(), name="admin-school-overview"),
    path("me/homework/", FacultyHomeworkView.as_view(), name="faculty-homework"),
    path("me/homework/<uuid:homework_id>/", FacultyHomeworkDetailView.as_view(),
         name="faculty-homework-detail"),
    path("student/homework/", StudentHomeworkView.as_view(), name="student-homework"),
]
