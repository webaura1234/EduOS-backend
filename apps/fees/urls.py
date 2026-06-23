"""URL configuration for the fees app."""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.fees.views import (
    BranchFeeLedgerView,
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
    StudentPortalFeesView,
    StudentPortalReceiptsView,
    VerifyPaymentCaptureView,
)

from apps.fees.views.admin_overview import AdminFeesOverviewView
from apps.fees.views.admin_payment import AdminRecordPaymentByStudentView

app_name = "fees"

router = DefaultRouter()
router.register("structures", FeeStructureViewSet, basename="structures")
router.register("concession-rules", ConcessionRuleViewSet, basename="concession-rules")
router.register("concession-requests", ConcessionRequestViewSet, basename="concession-requests")
router.register("credit-notes", CreditNoteViewSet, basename="credit-notes")
router.register("refunds", RefundViewSet, basename="refunds")

urlpatterns = [
    path("", include(router.urls)),

    # Admin aggregate (FeesData shape) + record-payment-by-student
    path("admin-overview/", AdminFeesOverviewView.as_view(), name="admin-overview"),
    path("payments/offline-by-student/", AdminRecordPaymentByStudentView.as_view(), name="offline-by-student"),

    # Invoices & Assignments
    path("assignments/", StudentFeeAssignmentView.as_view(), name="assignments"),
    path("invoices/generate/", GenerateInvoicesView.as_view(), name="invoices-generate"),
    
    # Dashboards & Ops
    path("collection/", CollectionDashboardView.as_view(), name="collection"),
    path("defaulters/", DefaultersListView.as_view(), name="defaulters"),
    path("branches/<uuid:branch_id>/ledger/", BranchFeeLedgerView.as_view(), name="branch-ledger"),
    
    # Payments, Verify & Webhooks
    path("orders/", CreateOrderView.as_view(), name="orders"),
    path("payments/verify/", VerifyPaymentCaptureView.as_view(), name="payments-verify"),
    path("payments/offline/", RecordOfflinePaymentView.as_view(), name="payments-offline"),
    path("webhook/", RazorpayWebhookView.as_view(), name="webhook"),
    
    # Student Portal
    path("me/dues/", StudentPortalDuesView.as_view(), name="student-dues"),
    path("me/fees/", StudentPortalFeesView.as_view(), name="student-fees"),
    path("me/receipts/", StudentPortalReceiptsView.as_view(), name="student-receipts"),
    
    # Parent Portal
    path("children/<uuid:student_id>/dues/", ParentPortalChildDuesView.as_view(), name="parent-child-dues"),
    path("children/<uuid:student_id>/pay/", ParentPortalChildPayView.as_view(), name="parent-child-pay"),
]
