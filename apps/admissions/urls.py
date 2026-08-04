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
from apps.admissions.views.admin_tab_overview import (
    AdminAdmissionsEnquiriesTabView,
    AdminAdmissionsNotificationsTabView,
    AdminAdmissionsOverviewTabView,
    AdminAdmissionsPipelineTabView,
    AdminAdmissionsWaitlistTabView,
)
from apps.admissions.views.admin_enroll import AdminEnrollFromApplicationView
from apps.admissions.views.enquiry_form import (
    EnquiryFormView,
    PublicEnquiryFormView,
    PublicEnquirySubmitView,
)
from apps.admissions.views.student_import import (
    StudentImportColumnsView,
    StudentImportJobDetailView,
    StudentImportJobErrorsView,
    StudentImportJobListCreateView,
    StudentImportMappingDetailView,
    StudentImportMappingListCreateView,
    StudentImportTemplateCsvView,
    StudentImportTemplateXlsxView,
    StudentImportUploadView,
    StudentImportValidateView,
)

app_name = "admissions"

urlpatterns = [
    # Admin aggregate (AdmissionsData shape) + one-click enroll-from-application
    path("admin-overview/", AdminAdmissionsOverviewView.as_view(), name="admin-overview"),
    path("admin-overview/overview/", AdminAdmissionsOverviewTabView.as_view(), name="admin-overview-tab"),
    path("admin-overview/enquiries/", AdminAdmissionsEnquiriesTabView.as_view(), name="admin-enquiries-tab"),
    path("admin-overview/pipeline/", AdminAdmissionsPipelineTabView.as_view(), name="admin-pipeline-tab"),
    path("admin-overview/notifications/", AdminAdmissionsNotificationsTabView.as_view(), name="admin-notifications-tab"),
    path("admin-overview/waitlist/", AdminAdmissionsWaitlistTabView.as_view(), name="admin-waitlist-tab"),
    path("applications/<uuid:application_id>/enroll-from-application/",
         AdminEnrollFromApplicationView.as_view(), name="enroll-from-application"),

    # Enquiries
    # Configurable enquiry form (admin management + public shareable form)
    path("enquiry-form/", EnquiryFormView.as_view(), name="enquiry-form"),
    path("public/enquiry-form/", PublicEnquiryFormView.as_view(), name="public-enquiry-form"),
    path("public/enquiry/", PublicEnquirySubmitView.as_view(), name="public-enquiry-submit"),

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

    # Student bulk import
    path("student-imports/templates/csv/", StudentImportTemplateCsvView.as_view(), name="student-import-template-csv"),
    path("student-imports/templates/xlsx/", StudentImportTemplateXlsxView.as_view(), name="student-import-template-xlsx"),
    path("student-imports/columns/", StudentImportColumnsView.as_view(), name="student-import-columns"),
    path("student-imports/upload/", StudentImportUploadView.as_view(), name="student-import-upload"),
    path("student-imports/validate/", StudentImportValidateView.as_view(), name="student-import-validate"),
    path("student-imports/jobs/", StudentImportJobListCreateView.as_view(), name="student-import-jobs"),
    path("student-imports/jobs/<uuid:job_id>/", StudentImportJobDetailView.as_view(), name="student-import-job-detail"),
    path("student-imports/jobs/<uuid:job_id>/errors/", StudentImportJobErrorsView.as_view(), name="student-import-job-errors"),
    path("student-imports/mappings/", StudentImportMappingListCreateView.as_view(), name="student-import-mappings"),
    path("student-imports/mappings/<uuid:mapping_id>/", StudentImportMappingDetailView.as_view(), name="student-import-mapping-detail"),
]
