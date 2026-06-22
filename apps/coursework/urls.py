from django.urls import path

from apps.coursework.views import FacultyHomeworkView, StudentHomeworkView

app_name = "coursework"

urlpatterns = [
    path("me/homework/", FacultyHomeworkView.as_view(), name="faculty-homework"),
    path("student/homework/", StudentHomeworkView.as_view(), name="student-homework"),
]
