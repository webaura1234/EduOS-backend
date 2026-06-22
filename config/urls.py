"""
Root URL configuration for EduOS.

All API routes are namespaced under /api/v1/<app>/.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    # Admin
    path("admin/", admin.site.urls),
    # ── API v1 ──────────────────────────────────
    path("api/v1/auth/", include("apps.accounts.urls", namespace="accounts")),
    path("api/v1/organizations/", include("apps.organizations.urls", namespace="organizations")),
    path("api/v1/academics/", include("apps.academics.urls", namespace="academics")),
    path("api/v1/admissions/", include("apps.admissions.urls", namespace="admissions")),
    path("api/v1/attendance/", include("apps.attendance.urls", namespace="attendance")),
    path("api/v1/examinations/", include("apps.examinations.urls", namespace="examinations")),
    path("api/v1/fees/", include("apps.fees.urls", namespace="fees")),
    path("api/v1/hr/", include("apps.hr.urls", namespace="hr")),
    path("api/v1/communications/", include("apps.communications.urls", namespace="communications")),
    path("api/v1/grievances/", include("apps.grievances.urls", namespace="grievances")),
    path("api/v1/coursework/", include("apps.coursework.urls", namespace="coursework")),
    path("api/v1/analytics/", include("apps.analytics.urls", namespace="analytics")),
    path("api/v1/integrations/", include("apps.integrations.urls", namespace="integrations")),
    # ── Health checks ────────────────────────────
    path("health/", include("apps.core.urls", namespace="core")),
]
