"""Report and metrics interactors."""

from apps.fees.queries import report as report_q


class GetCollectionDashboardInteractor:
    """Calculates real-time collections dashboard metrics for a branch."""

    def __init__(self, branch_id):
        self.branch_id = branch_id

    def execute(self) -> dict:
        total_invoiced, total_collected = report_q.invoice_totals(self.branch_id)
        return {
            "totalInvoicedPaise": total_invoiced,
            "totalCollectedPaise": total_collected,
            "totalPendingPaise": max(total_invoiced - total_collected, 0),
            "totalRefundedPaise": report_q.total_refunded(self.branch_id),
            "totalConcessionsPaise": report_q.total_concessions(self.branch_id),
        }
