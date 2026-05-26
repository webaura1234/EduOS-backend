"""
URL configuration for the organizations app.
"""

from django.urls import path
from apps.organizations.views.tenant import TenantConfigView

app_name = "organizations"

urlpatterns = [
    path("tenant-config/", TenantConfigView.as_view(), name="tenant-config"),
]
