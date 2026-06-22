"""URL configuration for the grievances app (mounted at /api/v1/grievances/)."""

from django.urls import path

from apps.grievances.views import (
    AdminGrievanceActionView,
    AdminGrievancesView,
    StudentGrievancesView,
)

app_name = "grievances"

urlpatterns = [
    path("me/", StudentGrievancesView.as_view(), name="student-grievances"),
    path("", AdminGrievancesView.as_view(), name="admin-grievances"),
    path("actions/", AdminGrievanceActionView.as_view(), name="admin-actions"),
]
