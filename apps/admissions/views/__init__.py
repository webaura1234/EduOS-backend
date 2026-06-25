"""Admissions views."""

from apps.admissions.views.application import (
    ApplicationDetailView,
    ApplicationEnrollView,
    ApplicationListCreateView,
    ApplicationRejectView,
    ApplicationStatusView,
    ApplicationStepView,
    ApplicationDocumentView,
    DocumentVerifyView,
)
from apps.admissions.views.enquiry import (
    EnquiryConvertView,
    EnquiryDetailView,
    EnquiryListCreateView,
)
from apps.admissions.views.enrollment import (
    EnrollmentDetailView,
    EnrollmentListCreateView,
    EnrollmentTransferView,
    SiblingOverrideView,
)
from apps.admissions.views.funnel import FunnelAnalyticsView
from apps.admissions.views.waitlist import (
    CourseMeritListView,
    WaitlistListCreateView,
    WaitlistPromoteView,
)

__all__ = [
    "EnquiryListCreateView",
    "EnquiryDetailView",
    "EnquiryConvertView",
    "ApplicationListCreateView",
    "ApplicationDetailView",
    "ApplicationStepView",
    "ApplicationDocumentView",
    "DocumentVerifyView",
    "ApplicationRejectView",
    "ApplicationStatusView",
    "ApplicationEnrollView",
    "CourseMeritListView",
    "WaitlistListCreateView",
    "WaitlistPromoteView",
    "EnrollmentListCreateView",
    "EnrollmentDetailView",
    "EnrollmentTransferView",
    "SiblingOverrideView",
    "FunnelAnalyticsView",
]
