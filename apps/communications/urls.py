"""URL configuration for the communications app."""

from django.urls import path

from apps.communications.views.notification import NotificationPreferencesView

app_name = "communications"

urlpatterns = [
    path("notification-preferences/", NotificationPreferencesView.as_view(),
         name="notification-preferences"),
]
