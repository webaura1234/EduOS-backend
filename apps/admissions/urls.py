"""URL configuration for the admissions app."""

from django.urls import path

from apps.admissions.views import (
    ApplicationDetailView,
    ApplicationEnrollView,
    ApplicationListCreateView,
    ApplicationRejectView,
    ApplicationStatusView,
    ApplicationStepView,
    ApplicationDocumentView,
    DocumentVerifyView,
    CourseMeritListView,
    EnquiryConvertView,
    EnquiryDetailView,
    EnquiryListCreateView,
    EnrollmentDetailView,
    EnrollmentListCreateView,
    EnrollmentTransferView,
    SiblingOverrideView,
    FunnelAnalyticsView,
    WaitlistListCreateView,
    WaitlistPromoteView,
)
from apps.admissions.views.admin_overview import AdminAdmissionsOverviewView
from apps.admissions.views.admin_enroll import AdminEnrollFromApplicationView

app_name = "admissions"

urlpatterns = [
    # Admin aggregate (AdmissionsData shape) + one-click enroll-from-application
    path("admin-overview/", AdminAdmissionsOverviewView.as_view(), name="admin-overview"),
    path("applications/<uuid:application_id>/enroll-from-application/",
         AdminEnrollFromApplicationView.as_view(), name="enroll-from-application"),

    # Enquiries
    path("enquiries/", EnquiryListCreateView.as_view(), name="enquiry-list-create"),
    path("enquiries/<uuid:enquiry_id>/", EnquiryDetailView.as_view(), name="enquiry-detail"),
    path("enquiries/<uuid:enquiry_id>/convert/", EnquiryConvertView.as_view(), name="enquiry-convert"),

    # Applications
    path("applications/", ApplicationListCreateView.as_view(), name="application-list"),
    path("applications/<uuid:application_id>/", ApplicationDetailView.as_view(), name="application-detail"),
    path("applications/<uuid:application_id>/step/", ApplicationStepView.as_view(), name="application-step"),
    path("applications/<uuid:application_id>/documents/", ApplicationDocumentView.as_view(), name="application-documents"),
    path("documents/<uuid:document_id>/verify/", DocumentVerifyView.as_view(), name="document-verify"),
    path("applications/<uuid:application_id>/status/", ApplicationStatusView.as_view(), name="application-status"),
    path("applications/<uuid:application_id>/reject/", ApplicationRejectView.as_view(), name="application-reject"),
    path("applications/<uuid:application_id>/enroll/", ApplicationEnrollView.as_view(), name="application-enroll"),

    # Merit & Waitlist
    path("courses/<uuid:course_id>/merit-list/", CourseMeritListView.as_view(), name="course-merit-list"),
    path("waitlist/", WaitlistListCreateView.as_view(), name="waitlist-list-create"),
    path("waitlist/<uuid:waitlist_id>/promote/", WaitlistPromoteView.as_view(), name="waitlist-promote"),

    # Enrollments
    path("enrollments/", EnrollmentListCreateView.as_view(), name="enrollment-list-create"),
    path("enrollments/<uuid:enrollment_id>/", EnrollmentDetailView.as_view(), name="enrollment-detail"),
    path("enrollments/<uuid:enrollment_id>/transfer/", EnrollmentTransferView.as_view(), name="enrollment-transfer"),
    path("enrollments/sibling-override/", SiblingOverrideView.as_view(), name="sibling-override"),

    # Analytics
    path("funnel/", FunnelAnalyticsView.as_view(), name="funnel-analytics"),
]
