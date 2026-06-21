"""URL configuration for the analytics app."""

from django.urls import path

from apps.analytics.views.audit import AuditLogListView, AuditVerifyView
from apps.analytics.views.dashboard import (
    AdminDashboardView,
    CollectionDashboardView,
    SuperAdminDashboardView,
    StudentDashboardView,
)
from apps.analytics.views.report import NaacExportView, ReportCreateView, ReportDetailView

app_name = "analytics"

urlpatterns = [
    # Dashboards
    path("dashboard/admin/", AdminDashboardView.as_view(), name="dashboard-admin"),
    path("dashboard/collection/", CollectionDashboardView.as_view(), name="dashboard-collection"),
    path("dashboard/super-admin/", SuperAdminDashboardView.as_view(), name="dashboard-super-admin"),
    path("dashboard/student/", StudentDashboardView.as_view(), name="dashboard-student"),

    # Audit
    path("audit/", AuditLogListView.as_view(), name="audit-list"),
    path("audit/verify/", AuditVerifyView.as_view(), name="audit-verify"),

    # Reports
    path("reports/", ReportCreateView.as_view(), name="report-create"),
    path("reports/naac/", NaacExportView.as_view(), name="report-naac"),
    path("reports/<uuid:export_id>/", ReportDetailView.as_view(), name="report-detail"),
]
