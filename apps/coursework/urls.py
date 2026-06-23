from django.urls import path

from apps.coursework.views import (
    FacultyHomeworkDetailView,
    FacultyHomeworkView,
    StudentHomeworkView,
)

app_name = "coursework"

urlpatterns = [
    path("me/homework/", FacultyHomeworkView.as_view(), name="faculty-homework"),
    path("me/homework/<uuid:homework_id>/", FacultyHomeworkDetailView.as_view(),
         name="faculty-homework-detail"),
    path("student/homework/", StudentHomeworkView.as_view(), name="student-homework"),
]
