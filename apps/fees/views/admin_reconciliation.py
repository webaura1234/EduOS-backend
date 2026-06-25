"""Admin: reconcile pending Razorpay payments for a branch."""

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.academics.scoping import resolve_branch
from apps.accounts.permissions import IsAdminOrSuperAdmin
from apps.fees.interactors.reconciliation import ReconcilePendingPaymentInteractor
from apps.fees.views.admin_overview import _reconciliation_list


class AdminReconcilePaymentsView(APIView):
    """POST → poll gateway for stuck pending payments; GET → current reconciliation list."""
    permission_classes = [IsAuthenticated, IsAdminOrSuperAdmin]

    def get(self, request) -> Response:
        branch = resolve_branch(request)
        return Response({"reconciliation": _reconciliation_list(branch)})

    def post(self, request) -> Response:
        branch = resolve_branch(request)
        count = ReconcilePendingPaymentInteractor(branch.pk).execute()
        return Response({
            "reconciledCount": count,
            "reconciliation": _reconciliation_list(branch),
        })
