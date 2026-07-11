"""URL configuration for the communications app."""

from django.urls import path

from apps.communications.views.announcement import (
    AdminAnnouncementsView,
    FacultyAnnouncementsView,
    StudentAnnouncementsUnreadView,
    StudentAnnouncementsView,
)
from apps.communications.views.inbox import (
    NotificationBranchRecentView,
    NotificationListView,
    NotificationMarkAllReadView,
    NotificationMarkReadView,
    NotificationUnreadCountView,
)
from apps.communications.views.notification import NotificationPreferencesView

app_name = "communications"

urlpatterns = [
    path("notification-preferences/", NotificationPreferencesView.as_view(),
         name="notification-preferences"),
    path("notifications/", NotificationListView.as_view(), name="notifications"),
    path("notifications/unread-count/", NotificationUnreadCountView.as_view(),
         name="notifications-unread-count"),
    path("notifications/mark-all-read/", NotificationMarkAllReadView.as_view(),
         name="notifications-mark-all-read"),
    path("notifications/branch-recent/", NotificationBranchRecentView.as_view(),
         name="notifications-branch-recent"),
    path("notifications/<uuid:notification_id>/read/", NotificationMarkReadView.as_view(),
         name="notification-mark-read"),
    path("announcements/", AdminAnnouncementsView.as_view(), name="announcements"),
    path("announcements/me/", StudentAnnouncementsView.as_view(), name="student-announcements"),
    path("announcements/me/unread-count/", StudentAnnouncementsUnreadView.as_view(),
         name="student-announcements-unread"),
    path("announcements/faculty/", FacultyAnnouncementsView.as_view(), name="faculty-announcements"),
]
