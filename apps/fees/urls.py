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
    ParentPortalChildFeesView,
    ParentPortalChildPayView,
    RazorpayWebhookView,
    RecordOfflinePaymentView,
    RefundViewSet,
    StudentConcessionViewSet,
    StudentFeeAssignmentView,
    StudentPortalDuesView,
    StudentPortalFeesView,
    StudentPortalReceiptsView,
    VerifyPaymentCaptureView,
    WriteOffInvoiceView,
)

from apps.fees.views.fee_head import FeeHeadViewSet
from apps.fees.views.structure_actions import (
    FeeStructureArchiveView,
    FeeStructureImpactView,
    FeeStructureNewVersionView,
    FeeStructurePublishView,
)
from apps.fees.views.admin_overview import AdminFeesOverviewView
from apps.fees.views.admin_tab_overview import (
    AdminFeesCollectionsTabView,
    AdminFeesConcessionsTabView,
    AdminFeesDefaultersTabView,
    AdminFeesInstallmentsTabView,
    AdminFeesInvoicesTabView,
    AdminFeesReconciliationTabView,
    AdminFeesRefundsTabView,
    AdminFeesScholarshipsTabView,
    AdminFeesStructureTabView,
)
from apps.fees.views.admin_payment import AdminRecordPaymentByStudentView
from apps.fees.views.admin_payments_list import AdminPaymentsListView, AdminPaymentsSummaryView
from apps.fees.views.admin_reconciliation import AdminReconcilePaymentsView
from apps.fees.views.receipt import ReceiptDownloadView
from apps.fees.views.self_export import StudentFeeStatementExportView

app_name = "fees"

router = DefaultRouter()
router.register("fee-heads", FeeHeadViewSet, basename="fee-heads")
router.register("structures", FeeStructureViewSet, basename="structures")
router.register("concession-rules", ConcessionRuleViewSet, basename="concession-rules")
router.register("student-concessions", StudentConcessionViewSet, basename="student-concessions")
router.register("concession-requests", ConcessionRequestViewSet, basename="concession-requests")
router.register("credit-notes", CreditNoteViewSet, basename="credit-notes")
router.register("refunds", RefundViewSet, basename="refunds")

urlpatterns = [
    path("", include(router.urls)),

    # Admin aggregate (FeesData shape) + record-payment-by-student
    path("admin-overview/", AdminFeesOverviewView.as_view(), name="admin-overview"),
    path("admin-overview/structure/", AdminFeesStructureTabView.as_view(), name="admin-structure-tab"),
    path("admin-overview/concessions/", AdminFeesConcessionsTabView.as_view(), name="admin-concessions-tab"),
    path("admin-overview/collections/", AdminFeesCollectionsTabView.as_view(), name="admin-collections-tab"),
    path("admin-overview/defaulters/", AdminFeesDefaultersTabView.as_view(), name="admin-defaulters-tab"),
    path("admin-overview/installments/", AdminFeesInstallmentsTabView.as_view(), name="admin-installments-tab"),
    path("admin-overview/reconciliation/", AdminFeesReconciliationTabView.as_view(), name="admin-reconciliation-tab"),
    path("admin-overview/refunds/", AdminFeesRefundsTabView.as_view(), name="admin-refunds-tab"),
    path("admin-overview/scholarships/", AdminFeesScholarshipsTabView.as_view(), name="admin-scholarships-tab"),
    path("admin-overview/invoices/", AdminFeesInvoicesTabView.as_view(), name="admin-invoices-tab"),
    path("admin-payments/", AdminPaymentsListView.as_view(), name="admin-payments-list"),
    path("admin-payments/summary/", AdminPaymentsSummaryView.as_view(), name="admin-payments-summary"),
    path("payments/offline-by-student/", AdminRecordPaymentByStudentView.as_view(), name="offline-by-student"),
    path("reconciliation/run/", AdminReconcilePaymentsView.as_view(), name="reconciliation-run"),

    path("structures/<uuid:structure_id>/impact/", FeeStructureImpactView.as_view(), name="structure-impact"),
    path("structures/<uuid:structure_id>/publish/", FeeStructurePublishView.as_view(), name="structure-publish"),
    path("structures/<uuid:structure_id>/archive/", FeeStructureArchiveView.as_view(), name="structure-archive"),
    path("structures/<uuid:structure_id>/new-version/", FeeStructureNewVersionView.as_view(), name="structure-new-version"),

    # Invoices & Assignments
    path("assignments/", StudentFeeAssignmentView.as_view(), name="assignments"),
    path("invoices/generate/", GenerateInvoicesView.as_view(), name="invoices-generate"),
    
    path("invoices/<uuid:invoice_id>/write-off/", WriteOffInvoiceView.as_view(), name="invoice-write-off"),
    
    # Dashboards & Ops
    path("collection/", CollectionDashboardView.as_view(), name="collection"),
    path("defaulters/", DefaultersListView.as_view(), name="defaulters"),
    path("branches/<uuid:branch_id>/ledger/", BranchFeeLedgerView.as_view(), name="branch-ledger"),
    
    # Payments, Verify & Webhooks
    path("orders/", CreateOrderView.as_view(), name="orders"),
    path("payments/verify/", VerifyPaymentCaptureView.as_view(), name="payments-verify"),
    path("payments/offline/", RecordOfflinePaymentView.as_view(), name="payments-offline"),
    path("webhook/", RazorpayWebhookView.as_view(), name="webhook"),
    
    # Receipts
    path("receipts/<uuid:receipt_id>/download/", ReceiptDownloadView.as_view(), name="receipt-download"),

    # Student Portal
    path("me/dues/", StudentPortalDuesView.as_view(), name="student-dues"),
    path("me/fees/", StudentPortalFeesView.as_view(), name="student-fees"),
    path("me/receipts/", StudentPortalReceiptsView.as_view(), name="student-receipts"),
    path("me/exports/fee-statement/", StudentFeeStatementExportView.as_view(), name="student-export-fee-statement"),

    # Parent Portal
    path("children/<uuid:student_id>/fees/", ParentPortalChildFeesView.as_view(), name="parent-child-fees"),
    path("children/<uuid:student_id>/dues/", ParentPortalChildDuesView.as_view(), name="parent-child-dues"),
    path("children/<uuid:student_id>/pay/", ParentPortalChildPayView.as_view(), name="parent-child-pay"),
]
