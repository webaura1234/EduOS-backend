"""URL configuration for the communications app."""

from django.urls import path

from apps.communications.views.announcement import (
    AdminAnnouncementsView,
    FacultyAnnouncementsView,
    StudentAnnouncementsView,
)
from apps.communications.views.notification import NotificationPreferencesView

app_name = "communications"

urlpatterns = [
    path("notification-preferences/", NotificationPreferencesView.as_view(),
         name="notification-preferences"),
    path("announcements/", AdminAnnouncementsView.as_view(), name="announcements"),
    path("announcements/me/", StudentAnnouncementsView.as_view(), name="student-announcements"),
    path("announcements/faculty/", FacultyAnnouncementsView.as_view(), name="faculty-announcements"),
]
