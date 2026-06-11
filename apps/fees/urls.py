"""URL configuration for the fees app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.fees.views import (
    CollectionDashboardView,
    ConcessionRequestViewSet,
    ConcessionRuleViewSet,
    CreateOrderView,
    CreditNoteViewSet,
    DefaultersListView,
    FeeStructureViewSet,
    GenerateInvoicesView,
    ParentPortalChildDuesView,
    ParentPortalChildPayView,
    RazorpayWebhookView,
    RecordOfflinePaymentView,
    RefundViewSet,
    StudentFeeAssignmentView,
    StudentPortalDuesView,
    StudentPortalReceiptsView,
    VerifyPaymentCaptureView,
)

app_name = "fees"

router = DefaultRouter()
router.register("structures", FeeStructureViewSet, basename="structures")
router.register("concession-rules", ConcessionRuleViewSet, basename="concession-rules")
router.register("concession-requests", ConcessionRequestViewSet, basename="concession-requests")
router.register("credit-notes", CreditNoteViewSet, basename="credit-notes")
router.register("refunds", RefundViewSet, basename="refunds")

urlpatterns = [
    path("", include(router.urls)),
    
    # Invoices & Assignments
    path("assignments/", StudentFeeAssignmentView.as_view(), name="assignments"),
    path("invoices/generate/", GenerateInvoicesView.as_view(), name="invoices-generate"),
    
    # Dashboards & Ops
    path("collection/", CollectionDashboardView.as_view(), name="collection"),
    path("defaulters/", DefaultersListView.as_view(), name="defaulters"),
    
    # Payments, Verify & Webhooks
    path("orders/", CreateOrderView.as_view(), name="orders"),
    path("payments/verify/", VerifyPaymentCaptureView.as_view(), name="payments-verify"),
    path("payments/offline/", RecordOfflinePaymentView.as_view(), name="payments-offline"),
    path("webhook/", RazorpayWebhookView.as_view(), name="webhook"),
    
    # Student Portal
    path("me/dues/", StudentPortalDuesView.as_view(), name="student-dues"),
    path("me/receipts/", StudentPortalReceiptsView.as_view(), name="student-receipts"),
    
    # Parent Portal
    path("children/<uuid:student_id>/dues/", ParentPortalChildDuesView.as_view(), name="parent-child-dues"),
    path("children/<uuid:student_id>/pay/", ParentPortalChildPayView.as_view(), name="parent-child-pay"),
]
